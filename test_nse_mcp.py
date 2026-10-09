import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ============================================================
# FIND THE MCP SERVER
# ============================================================

PYTHON_DIR = Path(sys.executable).resolve().parent

SERVER = PYTHON_DIR / "indian-market-mcp.exe"


# ============================================================
# TEST
# ============================================================

async def main():

    print("=" * 70)
    print("NOVA -> INDIAN MARKET MCP CONNECTION TEST")
    print("=" * 70)

    print()
    print(f"Python : {sys.executable}")
    print(f"Server : {SERVER}")

    if not SERVER.exists():

        print()
        print("ERROR: MCP server executable not found.")
        print()
        print("Expected:")
        print(SERVER)

        return

    print()
    print("Starting Indian Market MCP...")

    server_params = StdioServerParameters(
        command=str(SERVER),
        args=[],
        env=None,
    )

    try:

        async with stdio_client(
            server_params
        ) as (
            read_stream,
            write_stream,
        ):

            print(
                "MCP process started."
            )

            async with ClientSession(
                read_stream,
                write_stream,
            ) as session:

                print(
                    "Initializing MCP session..."
                )

                await session.initialize()

                print()
                print(
                    "MCP SESSION: CONNECTED"
                )

                print()
                print("=" * 70)
                print("AVAILABLE MARKET TOOLS")
                print("=" * 70)

                result = await session.list_tools()

                if not result.tools:

                    print(
                        "No MCP tools were returned."
                    )

                    return

                for number, tool in enumerate(
                    result.tools,
                    start=1,
                ):

                    print()
                    print(
                        f"{number}. {tool.name}"
                    )

                    if tool.description:

                        description = (
                            tool.description
                            .replace(
                                "\n",
                                " "
                            )
                            .strip()
                        )

                        print(
                            f"   {description[:500]}"
                        )

                print()
                print("=" * 70)
                print(
                    f"TOTAL TOOLS: "
                    f"{len(result.tools)}"
                )
                print("=" * 70)

    except Exception as exc:

        print()
        print("=" * 70)
        print("MCP CONNECTION FAILED")
        print("=" * 70)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        print()
        print("Server path used:")
        print(SERVER)

        raise


if __name__ == "__main__":

    asyncio.run(main())