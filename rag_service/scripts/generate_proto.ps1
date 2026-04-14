param(
    [string]$Root = "D:\codes\sanbox"
)

$protoDir = Join-Path $Root "rag_service\proto"

python -m grpc_tools.protoc `
  -I "$protoDir" `
  --python_out "$protoDir" `
  --grpc_python_out "$protoDir" `
  "$protoDir\rag.proto"

