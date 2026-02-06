import asyncio
from src.network.p2p_node import P2PNode

async def main():
    node = P2PNode(
        "Node1",
        "127.0.0.1",
        9000,
        8468,
        "storage/node1"
    )
    await node.initialize()
    node.start_server()
    print("✓ Node running!")
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
