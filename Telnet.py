# see also https://docs.python.org/3.12/library/telnetlib.html
# 

import time
from tango import AttrQuality, AttrWriteType, DispLevel, DevState, Attr, CmdArgType, UserDefaultAttrProp
from tango.server import Device, attribute, command, DeviceMeta
from tango.server import class_property, device_property
from tango.server import run
import os
import json
from threading import Thread
import datetime
import telnetlib
import re
from json import JSONDecodeError

class Telnet(Device, metaclass=DeviceMeta):
    pass

    host = device_property(dtype=str, default_value="127.0.0.1")
    username = device_property(dtype=str, default_value="")
    username_prompt = device_property(dtype=str, default_value="Username:")
    password = device_property(dtype=str, default_value="")
    password_prompt = device_property(dtype=str, default_value="Password:")
    port = device_property(dtype=int, default_value=23)
    init_command = device_property(dtype=str, default_value="")
    read_command = device_property(dtype=str, default_value="GET _VARNAME_\n")
    write_command = device_property(dtype=str, default_value="SET _VARNAME_ TO _VALUE_\n")
    init_dynamic_attributes = device_property(dtype=str, default_value="")
    prompt = device_property(dtype=str, default_value="> ")
    client = 0
    dynamicAttributes = {}
    
    @attribute
    def time(self):
        return time.time()

    @command(dtype_in=str)
    def add_dynamic_attribute(self, topic, 
            variable_type_name="DevString", min_value="", max_value="",
            unit="", write_type_name=""):
        if topic == "": return
        prop = UserDefaultAttrProp()
        variableType = self.stringValueToVarType(variable_type_name)
        writeType = self.stringValueToWriteType(write_type_name)
        if(min_value != "" and min_value != max_value): 
            prop.set_min_value(min_value)
        if(max_value != "" and min_value != max_value): 
            prop.set_max_value(max_value)
        if(unit != ""): 
            prop.set_unit(unit)
        attr = Attr(topic, variableType, writeType)
        attr.set_default_properties(prop)
        self.add_attribute(attr, r_meth=self.read_dynamic_attr, w_meth=self.write_dynamic_attr)
        self.dynamicAttributes[topic] = {"variableType": variableType, "value": 0 }
        print("added dynamic attribute " + topic)
        print(self.dynamicAttributes[topic])

    def stringValueToVarType(self, variable_type_name) -> CmdArgType:
        if(variable_type_name == "DevBoolean"):
            return CmdArgType.DevBoolean
        if(variable_type_name == "DevLong"):
            return CmdArgType.DevLong
        if(variable_type_name == "DevDouble"):
            return CmdArgType.DevDouble
        if(variable_type_name == "DevFloat"):
            return CmdArgType.DevFloat
        if(variable_type_name == "DevString"):
            return CmdArgType.DevString
        if(variable_type_name == ""):
            return CmdArgType.DevString
        raise Exception("given variable_type '" + variable_type + "' unsupported, supported are: DevBoolean, DevLong, DevDouble, DevFloat, DevString")

    def stringValueToWriteType(self, write_type_name) -> AttrWriteType:
        if(write_type_name == "READ"):
            return AttrWriteType.READ
        if(write_type_name == "WRITE"):
            return AttrWriteType.WRITE
        if(write_type_name == "READ_WRITE"):
            return AttrWriteType.READ_WRITE
        if(write_type_name == "READ_WITH_WRITE"):
            return AttrWriteType.READ_WITH_WRITE
        if(write_type_name == ""):
            return AttrWriteType.READ_WRITE
        raise Exception("given write_type '" + write_type_name + "' unsupported, supported are: READ, WRITE, READ_WRITE, READ_WITH_WRITE")
    
    def read_dynamic_attr(self, attr):
        name = attr.get_name()
        self.writeTelnet(self.read_cmd(name))
        value = self.stringValueToTypeValue(name, self.readTillPrompt())
        self.debug_stream("read value " + str(name) + ": " + str(value))
        attr.set_value(value)
 
    def stringValueToTypeValue(self, name, val):
        if(self.dynamicAttributes[name]["variableType"] == CmdArgType.DevBoolean):
            if(str(val).lower() == "false"):
                return False
            if(str(val).lower() == "true"):
                return True
            return bool(int(float(val)))
        if(self.dynamicAttributes[name]["variableType"] == CmdArgType.DevLong):
            return int(float(val))
        if(self.dynamicAttributes[name]["variableType"] == CmdArgType.DevDouble):
            return float(val)
        if(self.dynamicAttributes[name]["variableType"] == CmdArgType.DevFloat):
            return float(val)
        return val
        
    def write_dynamic_attr(self, attr):
        value = str(attr.get_write_value())
        name = attr.get_name()
        self.dynamicAttributes[name]["value"] = value
        self.publish(name)

    @command(dtype_in=[str])
    def publish(self, name):
        value = self.dynamicAttributes[name]["value"]
        self.info_stream("Publish variable " + str(name) + ": " + str(value))
        self.writeTelnet(self.write_cmd(name, value))
        print(self.readTillPrompt())


    def read_cmd(self, name):
        return self.read_command.replace("_VARNAME_", name)
        
    def write_cmd(self, name, value):
        return self.write_command.replace("_VARNAME_", name).replace("_VALUE_", str(value))
        
    def reconnect(self):
        self.client = telnetlib.Telnet(self.host, self.port, timeout=10)
        if(self.username != "" and self.username_prompt != ""):
            print("waiting for username prompt...")
            print(self.readTillPrompt(self.username_prompt))
            print("write to username prompt")
            self.writeTelnet(self.username)
        if(self.password != "" and self.password_prompt != ""):
            print("waiting for password prompt...")
            self.readTillPrompt(self.password_prompt)
            print("write to password prompt")
            self.writeTelnet(self.password)
        print("waiting for prompt...")
        print(self.readTillPrompt())
        if(self.init_command != ""):
            self.writeTelnet(self.init_command)
            print(self.readTillPrompt())

    def readTillPrompt(self, prompt = ""):
        if(prompt == ""):
            prompt = self.prompt
        out = self.client.read_until(prompt.encode('ascii')).decode('ascii')
        out = out.removesuffix(prompt)
        return out.strip()

    def writeTelnet(self, payload):
        self.client.write(payload.encode('ascii') + b"\n")
        
    def init_device(self):
        self.set_state(DevState.INIT)
        self.get_device_properties(self.get_device_class())
        self.info_stream("Connecting to " + str(self.host) + ":" + str(self.port))
        if self.init_dynamic_attributes != "":
            try:
                attributes = json.loads(self.init_dynamic_attributes)
                for attributeData in attributes:
                    self.add_dynamic_attribute(attributeData["name"], 
                        attributeData.get("data_type", ""), attributeData.get("min_value", ""), attributeData.get("max_value", ""),
                        attributeData.get("unit", ""), attributeData.get("write_type", ""))
            except JSONDecodeError as e:
                raise e
        self.reconnect()
        self.set_state(DevState.ON)

if __name__ == "__main__":
    deviceServerName = os.getenv("DEVICE_SERVER_NAME")
    run({deviceServerName: Telnet})
