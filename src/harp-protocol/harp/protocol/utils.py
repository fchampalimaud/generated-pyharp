from enum import IntFlag


class MessageTypeFlag(IntFlag):
    """
    Bit-mask flag to be used with the `MessageType` IntEnum.

    Attributes
    ----------
    ERROR : int
        Flag indicating that the message is an error message
    """

    ERROR = 0x08


class PayloadTypeFlag(IntFlag):
    """
    Internal flags used to define the PayloadType enumeration.

    Attributes
    ----------
    HAS_TIMESTAMP : int
        Flag indicating that the message has a timestamp
    IS_FLOAT : int
        Flag indicating that the message payload is a float
    IS_SIGNED : int
        Flag indicating that the message payload is signed
    TYPE_SIZE : int
        Mask to get the size of the message payload in bytes
    """

    HAS_TIMESTAMP = 0x10
    IS_FLOAT = 0x40
    IS_SIGNED = 0x80
    TYPE_SIZE = 0x0F
