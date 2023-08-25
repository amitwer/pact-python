import os

import grpc

import area_calculator_pb2
import area_calculator_pb2_grpc
from ffi_bridge import FfiBridge, LogLevel

protobuf_contract = {
    "pact:proto": os.path.abspath('../examples/proto/area_calculator.proto'),
    "pact:proto-service": 'Calculator/calculateOne',
    "pact:content-type": 'application/protobuf',
    "request": {
        "rectangle": {
            "length": 'matching(number,3)',
            "width": 'matching(number, 4)'
        }
    },
    "response": {
        "value": ['matching(number, 12)']
    }
}


def get_rectangle_area(address):
    print("Getting rectangle area.")
    with grpc.insecure_channel(address) as channel:
        stub = area_calculator_pb2_grpc.CalculatorStub(channel)
        rect = {
            "length": 3,
            "width": 4
        }
        response = stub.calculateOne(area_calculator_pb2.ShapeMessage(rectangle=rect))
    print(f"AreaCalculator client received: {response.value[0]}")
    return response.value[0]


def run_pact():
    bridge = FfiBridge()
    bridge.pact_version()
    bridge.init_logger(log_level=LogLevel.INFO)
    # bridge.log()
    bridge.log(source='pact_python_ffi', log_level=LogLevel.INFO,
               message=f"hello from pact python ffi, using Pact FFI Version {bridge.pact_version()}")

    bridge.log(source='pact_python_ffi', log_level=LogLevel.OFF,
               message="I don't expect to see this message")
    pact, message_pact = bridge.new_pact(consumer="amit-consumer", provider="amit-provider",
                                         description='amit-descriptions')
    # protobuf contract is request+expected_response
    bridge.use_protobuf(protobuf_contract=protobuf_contract, pact_handle=pact, message_pact=message_pact)
    mock_server_port = bridge.start_server(pact_handle=pact)

    # Make our client call
    expected_response = 12.0
    response = get_rectangle_area(f"localhost:{mock_server_port}")
    print(f"Client response: {response}")
    print(f"Client response - matched expected: {response == expected_response}")
    result = bridge.is_mock_server_matched()
    print(f"Pact - Got matching client requests: {result}")

    if result:
        pact_file_dir = './pacts'
        print(f"Writing pact file to {pact_file_dir}")
        bridge.write_pact_file(output_dir=pact_file_dir)
    else:
        print('pactffi_mock_server_matched did not match')
        bridge.get_mismatches()

    # Cleanup
    bridge.stop_server()


if __name__ == '__main__':
    run_pact()
