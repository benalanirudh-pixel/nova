import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():

    server = (
        Path(sys.executable).resolve().parent
        / "indian-market-mcp.exe"
    )

    params = StdioServerParameters(
        command=str(server),
        args=[],
        env=None,
    )

    async with stdio_client(params) as (
        read_stream,
        write_stream,
    ):

        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            result = await session.list_tools()

            wanted = {
                "get_stock_quote",
                "get_stock_history",
                "get_index",
                "get_all_indices",
                "get_index_history",
                "get_market_status",
                "get_fii_dii_data",
                "get_advances_declines",
                "get_sector_performance",
                "get_index_constituents",
                "get_option_chain",
                "get_pcr",
                "get_max_pain",
                "get_futures_data",
                "get_oi_data",
                "get_technical_indicators",
                "get_support_resistance",
                "get_top_gainers",
                "get_top_losers",
                "get_most_active_stocks",
                "get_bulk_deals",
                "get_shareholding_pattern",
            }

            print()
            print("=" * 90)
            print("NOVA — MARKET DATA TOOL SCHEMAS")
            print("=" * 90)

            for tool in result.tools:

                if tool.name not in wanted:
                    continue

                print()
                print("=" * 90)
                print(tool.name)
                print("=" * 90)

                print()

                schema = tool.inputSchema

                print(
                    "INPUT SCHEMA:"
                )

                print(
                    schema
                )

                if tool.description:

                    print()
                    print(
                        "DESCRIPTION:"
                    )

                    print(
                        tool.description
                    )

            print()
            print("=" * 90)
            print("SCHEMA EXTRACTION COMPLETE")
            print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())