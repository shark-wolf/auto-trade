import asyncio
import json
import sys

try:
    import websockets
except Exception as e:
    print("IMPORT_ERROR", e)
    sys.exit(1)


async def main():
    uri = 'ws://localhost:8765'
    try:
        async with websockets.connect(uri) as ws:
            msg = await ws.recv()
            print('WS_CONNECTED')
            s = msg if isinstance(msg, str) else msg.decode('utf-8', 'ignore')
            print('WS_PAYLOAD_HEAD', s[:200].replace('\n', ' '))
            return 0
    except Exception as e:
        print('WS_ERROR', str(e))
        return 1


if __name__ == '__main__':
    code = asyncio.run(main())
    sys.exit(code)