from enum import Enum

class TestState(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    READY = "ready"
    CONFIGURING = "configuring"
    UP = "up"
    VERIFYING = "verifying"
    TESTING = "testing"
    CLEANING = "cleaning"
    PASSED = "passed"
    FAILED = "failed"