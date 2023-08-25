import json
import logging
import os
from enum import Enum, auto
from typing import Tuple, Optional

from cffi import FFI

DIRECTIVES = [
    "#ifndef pact_ffi_h",
    "#define pact_ffi_h",
    "#include <stdarg.h>",
    "#include <stdbool.h>",
    "#include <stdint.h>",
    "#include <stdlib.h>",
    "#endif /* pact_ffi_h */"
]
log = logging.getLogger(__name__)


def _encode(s: str) -> bytes:
    return s.encode('utf-8')


class LogLevel(str, Enum):
    OFF = "off"
    ERROR = "error",
    WARN = "warn",
    INFO = "info",
    DEBUG = "debug",
    TRACE = "trace",


class PactSpecificationVersion(Enum):
    V1 = auto()
    V1_1 = auto()
    V2 = auto()
    V3 = auto()
    V4 = auto()


class FfiBridge:
    _mock_server_port: int
    _pact_handle: Optional["PactHandle"]

    @staticmethod
    def _process_pact_header_file(file_path: str):
        with open(file_path, "r") as fp:
            lines = fp.readlines()
        pactfile = []

        for line in lines:
            if line.strip("\n") not in DIRECTIVES:
                pactfile.append(line)

        return ''.join(pactfile)

    def __init__(self) -> None:
        log.debug("loading FFI functions")
        self._ffi = FFI()
        self._ffi.cdef(self._process_pact_header_file('../bin/pact.h'))
        self._lib = self._ffi.dlopen(os.path.abspath('../bin/pact_ffi.dll'))

    def pact_version(self) -> str:
        version_encoded = self._lib.pactffi_version()
        return self._ffi.string(version_encoded).decode('utf-8')

    def init_logger(self, log_level: LogLevel = LogLevel.INFO):
        log.debug("initializing logger to stdout")
        self._lib.pactffi_logger_init()
        self._lib.pactffi_logger_attach_sink(b'stdout', self._translate_log_level(log_level))
        self._lib.pactffi_logger_apply()
        log.debug("logger initialized")

    def log(self, message: str, source: str, log_level: LogLevel = LogLevel.INFO):
        if log_level != LogLevel.OFF:
            self._lib.pactffi_log_message(_encode(source), _encode(log_level), _encode(message))

    def new_pact(self, consumer: str,
                 provider: str,
                 description: str,
                 specification_version: PactSpecificationVersion = PactSpecificationVersion.V4) \
            -> Tuple["PactHandle", "InteractionHandle"]:
        pact = self._lib.pactffi_new_pact(_encode(consumer), _encode(provider))
        self._lib.pactffi_with_pact_metadata(pact, b'pact-python', b'ffi', self.pact_version().encode("utf-8"))
        message_pact = self._lib.pactffi_new_sync_message_interaction(pact, _encode(description))
        self._lib.pactffi_with_specification(pact,
                                             self._translate_spec_version(specification_version=specification_version))
        return pact, message_pact

    def _translate_spec_version(self, specification_version: PactSpecificationVersion):
        return {
            PactSpecificationVersion.V1: self._lib.PactSpecification_V1,
            PactSpecificationVersion.V1_1: self._lib.PactSpecification_V1_1,
            PactSpecificationVersion.V2: self._lib.PactSpecification_V2,
            PactSpecificationVersion.V3: self._lib.PactSpecification_V3,
            PactSpecificationVersion.V4: self._lib.PactSpecification_V4
        }[specification_version]

    def use_protobuf(self, protobuf_contract: dict, pact_handle: "PactHandle", message_pact):
        status_code = self._lib.pactffi_using_plugin(pact_handle, b'protobuf', b'0.3.4')
        assert status_code == 0
        status_code = self._lib.pactffi_interaction_contents(message_pact, 0, b'application/grpc',
                                                             self._ffi.new("char[]",
                                                                           json.dumps(protobuf_contract).encode(
                                                                               'ascii')))
        assert status_code == 0

    def start_server(self, pact_handle: "PactHandle"):
        self._mock_server_port = self._lib.pactffi_create_mock_server_for_transport(pact_handle, b'0.0.0.0', 0, b'grpc',
                                                                                    self._ffi.cast("void *", 0))
        self._pact_handle = pact_handle
        print(f"Mock server started: {self._mock_server_port}")
        return self._mock_server_port

    def stop_server(self):
        self._lib.pactffi_cleanup_mock_server(self._mock_server_port)
        self._lib.pactffi_cleanup_plugins(self._pact_handle)

    def _translate_log_level(self, log_level):
        return {
            LogLevel.OFF: self._lib.LevelFilter_Off,
            LogLevel.ERROR: self._lib.LevelFilter_Error,
            LogLevel.WARN: self._lib.LevelFilter_Warn,
            LogLevel.INFO: self._lib.LevelFilter_Info,
            LogLevel.DEBUG: self._lib.LevelFilter_Debug,
            LogLevel.TRACE: self._lib.LevelFilter_Trace,
        }[log_level]

    def is_mock_server_matched(self) -> bool:
        return self._lib.pactffi_mock_server_matched(self._mock_server_port)

    def write_pact_file(self, output_dir: str, overwrite: bool = True):
        status_code = self._lib.pactffi_write_pact_file(self._mock_server_port, output_dir.encode("ascii"), overwrite)
        if status_code != 0:
            raise RuntimeError(f"Could not write Pact file. Error code was {status_code}")

    def get_mismatches(self):
        mismatchers = self._lib.pactffi_mock_server_mismatches(self._mock_server_port)
        if mismatchers:
            log.debug("got mismatched traffic")
            return json.loads(self._ffi.string(mismatchers))
        return {}
