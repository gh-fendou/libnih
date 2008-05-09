#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# nih_dbus_tool.py - D-Bus binding generation tool
#
# Copyright © 2008 Scott James Remnant <scott@netsplit.com>.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA

import os
import re
import sys

from optparse import OptionParser
from xml.etree import ElementTree


# Replaced by autoconf-obtained strings
PACKAGE_NAME = "@PACKAGE_NAME@"
PACKAGE_COPYRIGHT = "@PACKAGE_COPYRIGHT@"

# Prefix for external functions
extern_prefix = "dbus"


# Conversion for external C names
NAME_RE = re.compile(r'([a-z0-9])([A-Z])')


# array type
# struct type
# variant type (at least fallback to requiring them to define the marshal?)

# async function marshalling
# (async function dispatch too)
#
# "proxy" mode:
#   function dispatch
#   - call a function, need a connection and destination path in mind
#     interface and name can be built-in to code
#   signal marshal
#   - called when a signal we're expecting happens, will have a message
#     object and will call a handler with that -- need an object equivalent,
#     "proxy" likely


class DBusType(object):
    """D-Bus type.

    This abstract class represents the base of all D-Bus types that we
    can handle.
    """

    @classmethod
    def fromElement(cls, elem):
        name = elem.get("name")
        if name is None:
            raise AttributeError, "Argument name may not be null"

        type = elem.get("type")
        if type is None:
            raise AttributeError, "Argument type may not be null"

        direction = elem.get("direction", "in")
        if direction not in ( "in", "out" ):
            raise AttributeError, "Direction must be 'in' or 'out'"

        # FIXME don't ignore rest of type
        type_cls = cls.typeOf(type[0])
        return type_cls.fromArgument(name, direction)

    @classmethod
    def fromArgument(cls, name, direction="in"):
        self = cls()
        self.name = name
        self.direction = direction

        return self

    @staticmethod
    def typeOf(code):
        """Return type for given type signature code."""
        if code == "y":
            return DBusByte
        elif code == "b":
            return DBusBoolean
        elif code == "n":
            return DBusInt16
        elif code == "q":
            return DBusUInt16
        elif code == "i":
            return DBusInt32
        elif code == "u":
            return DBusUInt32
        elif code == "x":
            return DBusInt64
        elif code == "t":
            return DBusUInt64
        elif code == "d":
            return DBusDouble
        elif code == "s":
            return DBusString
        elif code == "o":
            return DBusObjectPath
        elif code == "g":
            return DBusSignature
        # FIXME we have other types
        else:
            raise AttributeError, "Unknown or unhandled type '%s'" % code

    def signature(self):
        """Type signature.

        Returns a string containing the D-Bus type signature for this type.
        """
        return None

    def vars(self):
        """Variable type and name.

        Returns a list containing a single tuple of the C type used for this
        type and the name given when creating the instance.
        """
        return []

    def marshal(self, iter_name, error):
        """Marshalling code.

        Returns a string containing the code that will marshal from an
        iterator with the name given into a local variable with the
        type and name as returned by vars().
        """
        return None

    def dispatch(self, iter_name, error):
        """Dispatching code.

        Returns a string containing the code that will dispatch from a
        local variable with the type and name as returned by vars() to
        an iterator with the name given.
        """
        return None


class DBusBasicType(DBusType):
    """D-Bus basic type.

    This abstract class represents the base of all basic D-Bus types that
    we can handle.  These share the code to marshal from a DBusMessage into
    a variable and dispatch from a variable back into a DBusMessage.
    """

    def signature(self):
        """Type signature.

        Returns a string containing the D-Bus type signature for this type.
        """
        return self.dbus_code

    def vars(self):
        """Variable type and name.

        Returns a list containing a single tuple of the C type used for this
        type and the name given when creating the instance.
        """
        return [ ( self.c_type, self.name ) ]

    def marshal(self, iter_name, error):
        """Marshalling code.

        Returns a string containing the code that will marshal from an
        iterator with the name given into a local variable with the
        type and name as returned by vars().
        """
        return """\
if (dbus_message_iter_get_arg_type (&%s) != %s) {
%s
}

dbus_message_iter_get_basic (&%s, &%s);

dbus_message_iter_next (&%s);
""" % (iter_name, self.dbus_type, error, iter_name, self.name, iter_name)

    def dispatch(self, iter_name, error):
        """Dispatching code.

        Returns a string containing the code that will dispatch from a
        local variable with the type and name as returned by vars() to
        an iterator with the name given.
        """
        return """\
if (! dbus_message_iter_append_basic (&%s, %s, &%s)) {
%s
}
""" % (iter_name, self.dbus_type, self.name, error)


class DBusStringType(DBusBasicType):
    """D-Bus string type.

    This abstract class represents the base of all string-derived D-Bus types
    that we can handle.  These share the code to marshal from a DBusMessage
    into a variable, the code to dispatch from a variable back into a
    DBusMessage and the same basic C type.
    """
    c_type    = "const char *"


class DBusByte(DBusBasicType):
    """D-Bus byte.

    This class represents the D-Bus byte type and should be instantiated with
    the name of the variable.  It shares marshalling and dispatch code with
    the other basic types.
    """
    c_type    = "uint8_t"
    dbus_code = "y"
    dbus_type = "DBUS_TYPE_BYTE"

class DBusBoolean(DBusBasicType):
    """D-Bus boolean.

    This class represents the D-Bus boolean type and should be instantiated
    with the name of the variable.  It shares marshalling and dispatch code
    with the other basic types.
    """
    c_type    = "int"
    dbus_code = "b"
    dbus_type = "DBUS_TYPE_BOOLEAN"

class DBusInt16(DBusBasicType):
    """D-Bus 16-bit integer.

    This class represents the D-Bus int16 type and should be instantiated with
    the name of the variable.  It shares marshalling and dispatch code with
    the other basic types.
    """
    c_type     = "int16_t"
    dbus_code = "n"
    dbus_type = "DBUS_TYPE_INT16"

class DBusUInt16(DBusBasicType):
    """D-Bus 16-bit unsigned integer.

    This class represents the D-Bus uint16 type and should be instantiated with
    the name of the variable.  It shares marshalling and dispatch code with
    the other basic types.
    """
    c_type    = "uint16_t"
    dbus_code = "q"
    dbus_type = "DBUS_TYPE_UINT16"

class DBusInt32(DBusBasicType):
    """D-Bus 32-bit integer.

    This class represents the D-Bus int32 type and should be instantiated with
    the name of the variable.  It shares marshalling and dispatch code with
    the other basic types.
    """
    c_type    = "int32_t"
    dbus_code = "i"
    dbus_type = "DBUS_TYPE_INT32"

class DBusUInt32(DBusBasicType):
    """D-Bus 32-bit unsigned integer.

    This class represents the D-Bus uint32 type and should be instantiated with
    the name of the variable.  It shares marshalling and dispatch code with
    the other basic types.
    """
    c_type    = "uint32_t"
    dbus_code = "u"
    dbus_type = "DBUS_TYPE_UINT32"

class DBusInt64(DBusBasicType):
    """D-Bus 64-bit integer.

    This class represents the D-Bus int64 type and should be instantiated with
    the name of the variable.  It shares marshalling and dispatch code with
    the other basic types.
    """
    c_type    = "int64_t"
    dbus_code = "x"
    dbus_type = "DBUS_TYPE_INT64"

class DBusUInt64(DBusBasicType):
    """D-Bus 64-bit unsigned integer.

    This class represents the D-Bus uint64 type and should be instantiated with
    the name of the variable.  It shares marshalling and dispatch code with
    the other basic types.
    """
    c_type    = "uint64_t"
    dbus_code = "t"
    dbus_type = "DBUS_TYPE_UINT64"

class DBusDouble(DBusBasicType):
    """D-Bus double.

    This class represents the D-Bus double type and should be instantiated
    with the name of the variable.  It shares marshalling and dispatch code
    with the other basic types.
    """
    c_type    = "double"
    dbus_code = "d"
    dbus_type = "DBUS_TYPE_DOUBLE"

class DBusString(DBusStringType):
    """D-Bus string.

    This class represents the D-Bus string type and should be instantiated
    with the name of the variable.  It shares marshalling and dispatch code
    and underlying C type with the other string types.
    """
    dbus_type = "DBUS_TYPE_STRING"
    dbus_code = "s"

class DBusObjectPath(DBusStringType):
    """D-Bus object path.

    This class represents the D-Bus object path type and should be instantiated
    with the name of the variable.  It shares marshalling and dispatch code
    and underlying C type with the other string types.
    """
    dbus_type = "DBUS_TYPE_OBJECT_PATH"
    dbus_code = "o"

class DBusSignature(DBusStringType):
    """D-Bus type signature.

    This class represents the D-Bus signature type and should be instantiated
    with the name of the variable.  It shares marshalling and dispatch code
    and underlying C type with the other string types.
    """
    dbus_type = "DBUS_TYPE_SIGNATURE"
    dbus_code = "g"


class DBusGroup(DBusType):
    def __init__(self, types):
        self.types = types

    def signature(self):
        """Type signature.

        Returns a string containing the D-Bus type signature for this type.
        """
        signature = ""

        for type in self.types:
            signature += type.signature()

        return signature

    def vars(self):
        """Variable type and name.

        Returns a list containing tuples of C type and name for each type
        within this group.
        """
        vars = []

        for type in self.types:
            vars.extend(type.vars())

        return vars

    def marshal(self, iter_name, error):
        """Marshalling code.

        Returns a string containing the code that will marshal from an
        iterator with the name given into local variables with the
        types and names as returned by vars().
        """
        code = ""

        for type in self.types:
            if code:
                code += "\n"
            code += type.marshal(iter_name, error)

        if code:
            code += "\n"
        code += """\
if (dbus_message_iter_get_arg_type (&%s) != DBUS_TYPE_INVALID) {
%s
}
""" % (iter_name, error)

        return code

    def dispatch(self, iter_name, error):
        """Dispatching code.

        Returns a string containing the code that will dispatch from
        local variables with the types and names as returned by vars() to
        an iterator with the name given.
        """
        code = ""

        for type in self.types:
            if code:
                code += "\n"
            code += type.dispatch(iter_name, error)

        return code


class Generator(object):
    def staticPrototypes(self):
        """Static prototypes.

        Returns an array of static function prototypes which are normally
        placed in a block at the top of the source file.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        return []

    def externPrototypes(self):
        """Extern prototypes.

        Returns an array of extern function prototypes which are normally
        placed in a block at the top of the source file, in lieu of
        missing headers.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        return []

    def variables(self):
        """Variables.

        Returns an array of both static and exported global variables
        normally placed in a block at the top of the source file.

        Each variable is the code to define it, including any documentation
        and default value.
        """
        return []

    def functions(self):
        """Functions.

        Returns an array of both static and exported functions which
        consistute the bulk of the source file.

        Each function is the code to define it, including any documentation.
        """
        return []

    def definitions(self):
        """Definitions.

        Returns an array of structure and type definitions which are
        normally placed in a block in the header file.

        Each definition is the code to define it, including any documentation.
        """
        return []

    def exports(self):
        """Exports.

        Returns an array of prototypes for exported variables which are
        placed as a block inside the extern part of the header file.

        Each export is a (type, name) tuple.
        """
        return []

    def exportPrototypes(self):
        """Function prototypes.

        Returns an array of exported function prototypes which are normally
        placed in a block inside the extern part of the header file.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        return []


class Member(Generator):
    def __init__(self, interface, name):
        self.interface = interface
        self.name = name

    @property
    def c_name(self):
        return self.name

    @property
    def extern_name(self):
        return "_".join(( extern_prefix,
                          NAME_RE.sub("\\1_\\2", self.c_name).lower()))


class MemberWithArgs(Member):
    @classmethod
    def fromElement(cls, interface, elem):
        name = elem.get("name")
        if name is None:
            raise AttributeError, "Name may not be null"

        types = [ DBusType.fromElement(elem) for elem in elem.findall("arg") ]

        return cls(interface, name, types)

    def __init__(self, interface, name, types):
        super(MemberWithArgs, self).__init__(interface, name)

        self.types = types

    def argArray(self):
        """Argument array.

        Returns a string containing code to initialise the array of arguments
        used for nih_dbus_object_new().
        """
        code = """\
static const NihDBusArg %s[] = {
""" % "_".join([ self.interface.c_name, self.c_name, "args" ])

        array = []
        for type in self.types:
            if type.direction == "in":
                direction = "NIH_DBUS_ARG_IN"
            elif type.direction == "out":
                direction = "NIH_DBUS_ARG_OUT"

            array.append(( "\"%s\"" % type.name,
                           "\"%s\"" % type.signature(),
                           direction ))

        for line in lineup_array(array):
            code += indent("%s,\n" % line, 1)

        code += """\
	{ NULL }
};
"""
        return code

    def variables(self):
        """Variables.

        Returns an array of both static and exported global variables
        normally placed in a block at the top of the source file.

        Each variable is the code to define it, including any documentation
        and default value.
        """
        return [ self.argArray() ]


class Method(MemberWithArgs):
    def __init__(self, interface, name, types):
        super(Method, self).__init__(interface, name, types)

        self.in_args = DBusGroup([t for t in types if t.direction == "in"])
        self.out_args = DBusGroup([t for t in types if t.direction == "out"])

    def marshalPrototype(self):
        """Marshalling function prototype.

        Returns a (retval, name, args, attributes) tuple for the prototype
        of the marshaller function.
        """
        return ( "static DBusHandlerResult",
                 "_".join([ self.interface.c_name, self.c_name, "marshal" ]),
                 [ ( "NihDBusObject *", "object" ),
                   ( "NihDBusMessage *", "message" ) ],
                 None )

    def marshalFunction(self):
        """Marshalling function.

        Returns a string containing a marshaller function that takes
        arguments from a D-Bus message, calls a C handler function with
        them passed properly, then constructs a reply if successful.
        """
        name = "_".join([ self.interface.c_name, self.c_name, "marshal" ])
        code = """\
static DBusHandlerResult
%s (NihDBusObject  *object,
%s  NihDBusMessage *message)
{
""" % (name, " " * len(name))

        # Declare local variables for the iterator, reply and those needed
        # for both input and output arguments.
        vars = [ ( "DBusMessageIter", "iter" ),
                 ( "DBusMessage *", "reply = NULL" ) ]
        vars.extend(self.in_args.vars())
        vars.extend(self.out_args.vars())

        code += indent(''.join("%s;\n" % var for var in lineup_vars(vars)), 1)

        # Pre-amble for the function
        code += "\n"
        code += indent("""\
nih_assert (object != NULL);
nih_assert (message != NULL);
""", 1);

        # Marshal the input arguments into local variables
        code += "\n"
        code += indent("""\
/* Iterate the arguments to the message and marshal into arguments
 * for our own function call.
 */
dbus_message_iter_init (message->message, &iter);
""", 1)
        code += "\n"

        error = indent("""\
reply = dbus_message_new_error (message->message, DBUS_ERROR_INVALID_ARGS,
				"Invalid arguments to %s method");
if (! reply)
	return DBUS_HANDLER_RESULT_NEED_MEMORY;

goto send;
""" % (self.name, ), 1);
        code += indent(self.in_args.marshal("iter", error), 1)

        # Construct the function call
        args = [ "object->data", "message" ]
        args.extend(name for type, name in self.in_args.vars())
        args.extend("&%s" % name for type, name in self.out_args.vars())

        code += "\n"
        code += indent("""\
/* Call the handler function. */
if (%s (%s) < 0) {
	NihError *err;

	err = nih_error_get ();
	if (err->number == ENOMEM) {
		nih_free (err);

		return DBUS_HANDLER_RESULT_NEED_MEMORY;
	} else if (err->number == NIH_DBUS_ERROR) {
		NihDBusError *dbus_err = (NihDBusError *)err;

		reply = dbus_message_new_error (message->message,
						dbus_err->name,
						err->message);
		nih_free (err);

		if (! reply)
			return DBUS_HANDLER_RESULT_NEED_MEMORY;

		goto send;
	} else {
		reply = dbus_message_new_error (message->message,
						DBUS_ERROR_FAILED,
						err->message);
		nih_free (err);

		if (! reply)
			return DBUS_HANDLER_RESULT_NEED_MEMORY;

		goto send;
	}
}
""" % (self.extern_name, ", ".join(args)), 1)

        # Be well-behaved and make the function return immediately if no
        # reply is expected
        code += "\n"
        code += indent("""\
/* If the sender doesn't care about a reply, don't bother wasting
 * effort constructing and sending one.
 */
if (dbus_message_get_no_reply (message->message))
	return DBUS_HANDLER_RESULT_HANDLED;
""", 1);

        # Create reply and dispatch the local variables into output arguments
        code += "\n"
        code += indent("""\
/* Construct the reply message */
reply = dbus_message_new_method_return (message->message);
if (! reply)
	return DBUS_HANDLER_RESULT_NEED_MEMORY;

dbus_message_iter_init_append (reply, &iter);
""", 1);
        code += "\n"

        error = indent("""\
dbus_message_unref (reply);
return DBUS_HANDLER_RESULT_NEED_MEMORY;
""", 1);
        code += indent(self.out_args.dispatch("iter", error), 1)

        # Send the reply
        code += "\nsend:\n"
        code += indent("""\
/* Send the reply, appending it to the outgoing queue. */
if (! dbus_connection_send (message->conn, reply, NULL)) {
	dbus_message_unref (reply);
	return DBUS_HANDLER_RESULT_NEED_MEMORY;
}

dbus_message_unref (reply);

return DBUS_HANDLER_RESULT_HANDLED;
""", 1);

        code += "}\n";

        return code

    def handlerPrototype(self):
        """Handler function prototype.

        Returns a (retval, name, args, attributes) tuple for the prototype
        of the handler function that the user must define.
        """
        vars = [ ("void *", "data"),
                 ("NihDBusMessage *", "message") ]
        vars.extend(self.in_args.vars())

        for type, name in self.out_args.vars():
            if type.endswith("*"):
                vars.append((type + "*", name))
            else:
                vars.append((type + " *", name))

        return ( "extern int",
                 self.extern_name,
                 vars,
                 None )

    def staticPrototypes(self):
        """Static prototypes.

        Returns an array of static function prototypes which are normally
        placed in a block at the top of the source file.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        return [ self.marshalPrototype() ]

    def externPrototypes(self):
        """Extern prototypes.

        Returns an array of extern function prototypes which are normally
        placed in a block at the top of the source file, in lieu of
        missing headers.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        return [ self.handlerPrototype() ]

    def functions(self):
        """Functions.

        Returns an array of both static and exported functions which
        consistute the bulk of the source file.

        Each function is the code to define it, including any documentation.
        """
        return [ self.marshalFunction() ]


class Signal(MemberWithArgs):
    def __init__(self, interface, name, types):
        super(Signal, self).__init__(interface, name, types)

        self.args = DBusGroup(types)

    def dispatchPrototype(self):
        """Dispatch function prototype.

        Returns a (retval, name, args, attributes) tuple for the prototype
        of the dispatch function.
        """
        vars = [ ( "DBusConnection *", "connection" ),
                 ( "const char *", "origin_path" ) ]
        vars.extend(self.args.vars())

        return ( "int",
                 self.extern_name,
                 vars,
                 ( "warn_unused_result", ) )

    def dispatchFunction(self):
        """Dispatch function.

        Returns a string containing a dispatch function that takes puts
        its arguments into a D-Bus message and sends it.
        """
        vars = [ ( "DBusConnection *", "connection" ),
                 ( "const char *", "origin_path" ) ]
        vars.extend(self.args.vars())

        code = "int\n%s (" % (self.extern_name, )
        code += (",\n" + " " * (len(self.extern_name) + 2)).join(lineup_vars(vars))
        code += ")\n{\n"

        # Declare local variables for the message and iterator
        vars = [ ( "DBusMessage *", "message"),
                 ( "DBusMessageIter", "iter" ) ]
        code += indent(''.join("%s;\n" % var for var in lineup_vars(vars)), 1)

        # Pre-amble for the function
        code += "\n"
        code += indent("""\
nih_assert (connection != NULL);
nih_assert (origin_path != NULL);
""", 1);

        # Marshal the arguments into a new local message
        code += "\n"
        code += indent("""\
message = dbus_message_new_signal (origin_path, "%s", "%s");
if (! message)
	return -1;

/* Iterate the arguments to the function and dispatch into
 * message arguments.
 */
dbus_message_iter_init_append (message, &iter);
""" % (self.interface.name, self.name), 1)
        code += "\n"

        error = indent("""\
dbus_message_unref (message);
return -1;
""", 1);
        code += indent(self.args.dispatch("iter", error), 1)

        code += "\n"
        code += indent("""\
/* Send the reply, appending it to the outgoing queue. */
if (! dbus_connection_send (connection, message, NULL)) {
	dbus_message_unref (message);
	return -1;
}

dbus_message_unref (message);

return 0;
""", 1)

        code += "}\n";

        return code

    def functions(self):
        """Functions.

        Returns an array of both static and exported functions which
        consistute the bulk of the source file.

        Each function is the code to define it, including any documentation.
        """
        return [ self.dispatchFunction() ]

    def exportPrototypes(self):
        """Function prototypes.

        Returns an array of exported function prototypes which are normally
        placed in a block inside the extern part of the header file.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        return [ self.dispatchPrototype() ]


class Group(Generator):
    def __init__(self, members):
        self.members = members

    def staticPrototypes(self):
        """Static prototypes.

        Returns an array of static function prototypes which are normally
        placed in a block at the top of the source file.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        prototypes = []
        for member in self.members:
            prototypes.extend(member.staticPrototypes())

        return prototypes

    def externPrototypes(self):
        """Extern prototypes.

        Returns an array of extern function prototypes which are normally
        placed in a block at the top of the source file, in lieu of
        missing headers.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        prototypes = []
        for member in self.members:
            prototypes.extend(member.externPrototypes())

        return prototypes

    def variables(self):
        """Variables.

        Returns an array of both static and exported global variables
        normally placed in a block at the top of the source file.

        Each variable is the code to define it, including any documentation
        and default value.
        """
        variables = []
        for member in self.members:
            variables.extend(member.variables())

        return variables

    def functions(self):
        """Functions.

        Returns an array of both static and exported functions which
        consistute the bulk of the source file.

        Each function is the code to define it, including any documentation.
        """
        functions = []
        for member in self.members:
            functions.extend(member.functions())

        return functions

    def definitions(self):
        """Definitions.

        Returns an array of structure and type definitions which are
        normally placed in a block in the header file.

        Each definition is the code to define it, including any documentation.
        """
        definitions = []
        for member in self.members:
            definitions.extend(member.definitions())

        return definitions

    def exports(self):
        """Exports.

        Returns an array of prototypes for exported variables which are
        placed as a block inside the extern part of the header file.

        Each export is a (type, name) tuple.
        """
        exports = []
        for member in self.members:
            exports.extend(member.exports())

        return exports

    def exportPrototypes(self):
        """Function prototypes.

        Returns an array of exported function prototypes which are normally
        placed in a block inside the extern part of the header file.

        Each prototype is a (retval, name, args, attributes) tuple.
        """
        prototypes = []
        for member in self.members:
            prototypes.extend(member.exportPrototypes())

        return prototypes


class Interface(Group):
    @classmethod
    def fromElement(cls, elem):
        name = elem.get("name")
        if name is None:
            raise AttributeError, "Interface name may not be null"

        self = cls(name, [])
        for e in elem.findall("method"):
            method = Method.fromElement(self, e)
            self.methods.append(method)
            self.members.append(method)
        for e in elem.findall("signal"):
            signal = Signal.fromElement(self, e)
            self.signals.append(signal)
            self.members.append(signal)

        return self

    def __init__(self, name, members):
        super(Interface, self).__init__(members)

        self.name = name
        self.methods = []
        self.signals = []

    @property
    def c_name(self):
        return self.name.replace(".", "_")

    def methodsArray(self):
        """Methods array.

        Returns a string containing code to initialise the array of methods
        used for nih_dbus_object_new().
        """
        code = """\
const NihDBusMethod %s_methods[] = {
""" % self.c_name

        array = []
        for method in self.methods:
            array.append(( "\"%s\"" % method.name,
                           "%s_marshal" % "_".join([ self.c_name, method.c_name ]),
                           "%s_args" % "_".join([ self.c_name, method.c_name ])))

        for line in lineup_array(array):
            code += indent("%s,\n" % line, 1)

        code += """\
	{ NULL }
};
"""
        return code

    def signalsArray(self):
        """Signals array.

        Returns a string containing code to initialise the array of signals
        used for nih_dbus_object_new().
        """
        code = """\
const NihDBusSignal %s_signals[] = {
""" % self.c_name

        array = []
        for signal in self.signals:
            array.append(( "\"%s\"" % signal.name,
                           "%s_args" % "_".join([ self.c_name, signal.c_name ])))

        for line in lineup_array(array):
            code += indent("%s,\n" % line, 1)

        code += """\
	{ NULL }
};
"""
        return code

    def interfacePrototype(self):
        """Interface structure prototype.

        Returns a (type, name) tuple for the prototype of the interface
        struct.
        """
        return ( "const NihDBusInterface", "%s" % self.c_name )

    def interfaceStruct(self):
        """Interface structure.

        Returns a string containing code to define a structure containing
        information about the interface.
        """
        code = """\
const NihDBusInterface %s = {
	\"%s\",
	%s_methods,
	%s_signals,
	NULL
""" % (self.c_name, self.name, self.c_name, self.c_name)

        code += """\
};
"""
        return code

    def variables(self):
        """Variables.

        Returns an array of both static and exported global variables
        normally placed in a block at the top of the source file.

        Each variable is the code to define it, including any documentation
        and default value.
        """
        variables = super(Interface, self).variables()
        variables.append(self.methodsArray())
        variables.append(self.signalsArray())
        variables.append(self.interfaceStruct())

        return variables

    def exports(self):
        """Exports.

        Returns an array of prototypes for exported variables which are
        placed as a block inside the extern part of the header file.

        Each export is a (type, name) tuple.
        """
        exports = super(Interface, self).exports()
        exports.append(self.interfacePrototype())

        return exports


class Output(Group):
    def __init__(self, basename, members):
        super(Output, self).__init__(members)

        self.basename = basename

    def sourceFile(self):
        """Generate source (.c) file.

        Returns a string containing the code for the source (.c) file
        of this code group.
        """
        code = """\
/* %s
 *
 * %s - %s
 *
 * %s
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
 */
""" % (PACKAGE_NAME, "%s.c" % self.basename, "Auto-generated d-bus bindings",
       PACKAGE_COPYRIGHT)

        # Usual includes
        if code:
            code += "\n"
        code += """\
#ifdef HAVE_CONFIG_H
# include <config.h>
#endif /* HAVE_CONFIG_H */


#include <dbus/dbus.h>

#include <errno.h>

#include <nih/macros.h>
#include <nih/alloc.h>
#include <nih/logging.h>
#include <nih/error.h>
#include <nih/errors.h>
#include <nih/dbus.h>

#include "%s.h"
""" % (self.basename, )

        # Extern function prototypes
        protos = self.externPrototypes()
        if protos:
            if code:
                code += "\n\n"
            code += """\
/* Prototypes for handler functions */
"""
            for line in lineup_protos(protos):
                code += line
                code += ";\n"

        # Static function prototypes
        protos = self.staticPrototypes()
        if protos:
            if code:
                code += "\n\n"
            code += """\
/* Prototypes for static functions */
"""
            for line in lineup_protos(protos):
                code += line
                code += ";\n"

        # Global variables
        variables = self.variables()
        if variables:
            if code:
                code += "\n"
            for g in variables:
                if code:
                    code += "\n"
                code += g

        # Function definitions
        functions = self.functions()
        if functions:
            if code:
                code += "\n"
            for function in functions:
                if code:
                    code += "\n"
                code += function

        return code

    def headerFile(self):
        """Generate header (.h) file.

        Returns a string containing the code for the header (.h) file
        of this code group.
        """
        code = """\
/* %s
 *
 * %s
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
 */
""" % (PACKAGE_NAME, PACKAGE_COPYRIGHT)

        # FIXME include sub-directory name in sentry?
        sentry = "DBUS__%s_H" % self.basename.replace(".", "_").upper()
        if code:
            code += "\n"
        code += """\
#ifndef %s
#define %s

#include <dbus/dbus.h>

#include <nih/macros.h>
#include <nih/dbus.h>
""" % (sentry, sentry)

        # Append structure definitions
        definitions = self.definitions()
        if definitions:
            if code:
                code += "\n"
            for definition in definitions:
                if code:
                    code += "\n"
                code += definition

        # Guard extern prototypes for C++ inclusion
        if code:
            code += "\n\n"
        code += """\
NIH_BEGIN_EXTERN
"""

        # Line up the variable prototypes together and place in a block
        globals = self.exports()
        if globals:
            if code:
                code += "\n"
            for line in lineup_vars(globals):
                code += line
                code += ";\n"

        # Line up the function prototypes together and place in a block
        protos = self.exportPrototypes()
        if protos:
            if code:
                code += "\n"
            for line in lineup_protos(protos):
                code += line
                code += ";\n"

        # End the extern guard and header sentry
        if code:
            code += "\n"
        code += """\
NIH_END_EXTERN

#endif /* %s */
""" % (sentry)

        return code


# Complex:
#  a (array) -> pointer of type, if type is pointer, last one NULL and length
#    (check type is array)
#    TYPE = dbus_message_iter_get_element_type (ITER)
#
#    dbus_message_iter_recurse (ITER, SUB)
#    dbus_message_iter_get_fixed_array (SUB, &value, &n_elements)
#    (or each type)
#    OK = dbus_message_iter_close_container (ITER, SUB)
#
#    dbus_message_iter_open_container (ITER, TYPE, NULL, SUB)
#    OK = dbus_message_iter_append_fixed_array (SUB, TYPE, &array, len)
#       note that it's the address of the array pointer, not the array pointer
#    (or each type)
#    OK = dbus_message_iter_close_container (ITER, SUB)
#
#
#  s (struct) -> pointer to a struct of a defined type (named after func + arg)
#       e.g. typedef struct job_find_by_name_what {
#               ...
#       } JobFindByNameWhat;
#
#    dbus_message_iter_recurse (ITER, SUB)
#    OK = dbus_message_iter_close_container (ITER, SUB)
#
#    dbus_message_iter_open_container (ITER, TYPE, NULL, SUB)
#    OK = dbus_message_iter_close_container (ITER, SUB)
#
# thus we can make arrays of it too :-)
# struct-in-struct can just get arbitrary names
#
#
# Annoying"
#  v (variant) -> seems to be a problem
#       has a type signature then the data
#
#  e (dict) -> problem for now (should be NihHash really)
#       always arrays a{..}
#       first type is basic
#       second type is any (including struct)


def lineup_vars(vars):
    """Lineup variable lists.

    Returns an array of lines of C code to declare each of the variables
    in vars, which should be an array of (type, name) tuples.  The
    declarations will be lined up in a pretty fashion.

    It is up to the caller to add appropriate line-endings.
    """
    exp_vars = []
    for type, name in vars:
        basic = type.rstrip("*")
        pointers = type[len(basic):]
        basic = basic.rstrip()
        exp_vars.append(( basic, pointers, name ))

    if not exp_vars:
        return []

    max_basic = max(len(b) for b,p,n in exp_vars)
    max_pointers = max(len(p) for b,p,n in exp_vars)

    lines = []
    for basic, pointers, name in exp_vars:
        code = basic.ljust(max_basic)
        code += pointers.rjust(max_pointers + 1)
        code += name

        lines.append(code)

    return lines

def lineup_protos(protos):
    """Lineup prototype lists.

    Returns an array of lines of C code to declare each of the prototypes
    in protos, which should be an array of (retval, name, args, attributes)
    tuples.  The declarations will be lined up in a pretty fashion.

    It is up to the caller to add appropriate line-endings.
    """
    if not protos:
        return []

    max_retval = max(len(r) for r,n,a,at in protos)
    max_name = max(len(n) for r,n,a,at in protos)

    if not [ True for r,n,a,at in protos if r.endswith("*") ]:
        max_retval += 1

    lines = []
    for retval, name, args, attributes in protos:
        code = retval.ljust(max_retval)
        code += name.ljust(max_name + 1)
        code += "("
        # FIXME split arguments over multiple lines maybe?
        code += ", ".join("%s%s%s" % (type, not type.endswith("*") and " " or "",
                                      name) for type,name in args)
        code += ")"
        if attributes:
            code += "\n\t__attribute__ ((" + ", ".join(attributes) + "))"

        lines.append(code)

    return lines

def lineup_array(array):
    """Lineup array definitions.

    Returns an array of lines of C code to declare each of the array struct
    definitions in array, which should be an array of tuples for each structure
    member.  The declarations will be lined up in a pretty fashion.

    It is up to the caller to add appropriate line-endings.
    """
    if not array:
        return []

    max_len = [ max(len(entry[i]) for entry in array)
                for i in range(0, len(array[0])) ]

    lines = []
    for entry in array:
        code = "{ "

        for i, str in enumerate(entry):
            if i < len(array[0]) - 1:
                code += (str + ", ").ljust(max_len[i] + 2)
            else:
                code += str.ljust(max_len[i])

        code += " }"

        lines.append(code)

    return lines


def indent(str, level):
    """Increase indent of string.

    Returns the string with each line indented to the given level of tabs.
    """
    output = ""
    for line in str.splitlines(True):
        if len(line.strip()):
            output += ("\t" * level) + line
        else:
            output += line
    return output


def main():
    global options
    global extern_prefix

    usage = "%prog [OPTION]... XMLFILE"
    description = """\
XMLFILE is a valid XML file containing information about one or more interfaces
in the D-Bus Introspection format, except that the top-level node may be
interface as well as node.

C code to marshal methods and dispatch signals (if --mode is object) or to
dispatch methods and marshal signals (if --mode is proxy) is written to
a .c and .h file in the current directory with the same base name as XMLFILE,
or to that specified by --output.
"""

    parser = OptionParser(usage, description=description)
    parser.add_option("--mode", type="string", metavar="MODE",
                      default="object",
                      help="Output mode: object, or proxy [default: %default]")
    parser.add_option("-o", "--output", type="string", metavar="FILENAME",
                      help="Write C source to FILENAME, header alongside")
    parser.add_option("--prefix", type="string", metavar="PREFIX",
                      default="dbus",
                      help="Prefix for externally supplied C functions [default: %default]")

    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("incorrect number of arguments")
    if options.mode not in ("object", "proxy"):
        parser.error("invalid mode")

    extern_prefix = options.prefix

    # Figure out input and output filenames based on arguments; try and
    # do the right thing in most circumstances
    xml_filename = args.pop(0)
    if options.output:
        (root, ext) = os.path.splitext(options.output)
        if ext and ext != ".h":
            source_filename = options.output
        else:
            source_filename = os.path.extsep.join(( root, "c" ))

        header_filename = os.path.extsep.join (( root, "h"))
        basename = os.path.basename(root)
    else:
        basename = os.path.splitext(os.path.basename(xml_filename))[0]
        source_filename = os.path.extsep.join(( basename, "c" ))
        header_filename = os.path.extsep.join(( basename, "h" ))

    (head, tail) = os.path.split(source_filename)
    tmp_source_filename = os.path.join(head, ".%s.tmp" % tail)

    (head, tail) = os.path.split(header_filename)
    tmp_header_filename = os.path.join(head, ".%s.tmp" % tail)


    # Parse the XML file into an ElementTree
    tree = ElementTree.parse(xml_filename)
    elem = tree.getroot()

    # Walk the tree to find interfaces
    interfaces = []
    if elem.tag == "interface":
        interfaces.append(Interface.fromElement(elem))
    else:
        for iface_e in elem.findall("interface"):
            interfaces.append(Interface.fromElement(iface_e))

    # Generate and write output
    o = Output(basename, interfaces)
    try:
        f = open(tmp_source_filename, "w")
        try:
            print >>f, o.sourceFile()
        finally:
            f.close()

        f = open(tmp_header_filename, "w")
        try:
            print >>f, o.headerFile()
        finally:
            f.close()

        os.rename(tmp_source_filename, source_filename)
        os.rename(tmp_header_filename, header_filename)
    except:
        if os.path.exists(tmp_source_filename):
            os.unlink(tmp_source_filename)
        if os.path.exists(tmp_header_filename):
            os.unlink(tmp_header_filename)

        raise


if __name__ == "__main__":
    main()