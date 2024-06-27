import os

import pytest

import boa
from boa import Env
from boa.rpc import to_bytes, to_int


@pytest.fixture(scope="module", autouse=True)
def forked_env(rpc_url):
    with boa.swap_env(Env()):
        boa.env.fork(rpc_url, block_identifier=20102743)
        yield


@pytest.fixture(scope="module")
def api_key():
    return os.environ.get("ETHERSCAN_API_KEY")


# https://app.blocksec.com/explorer/tx/eth/0xde001d295a15f427e613fa28adb12c8dbf6c03b9c1d647f438709eb444b747e8
def test_call_trace(api_key, get_filepath):
    # boa.from_etherscan(
    #     "0x004c167d27ada24305b76d80762997fa6eb8d9b2",
    #     name="CurveTwocryptoOptimized",
    #     api_key=api_key,
    # )
    twocrypto = boa.load_partial(get_filepath("CurveTwoCryptoOptimized.vy")).at(
        "0x004c167d27ada24305b76d80762997fa6eb8d9b2"
    )
    boa.from_etherscan(
        "0x2005995a71243be9fb995dab4742327dc76564df",
        name="CurveTwocryptoMathOptimized",
        api_key=api_key,
    )
    boa.from_etherscan(
        "0x9e7ae8bdba9aa346739792d219a808884996db67",
        name="EIP173Proxy",
        api_key=api_key,
    )
    settlement = boa.from_etherscan(
        "0x9008d19f58aabd9ed0d60971565aa8510560ab41",
        name="GPv2Settlement",
        api_key=api_key,
    )
    cvg = boa.from_etherscan(
        "0x97effb790f2fbb701d88f89db4521348a2b77be8", name="Cvg", api_key=api_key
    )
    boa.from_etherscan(
        "0x9e7ae8bdba9aa346739792d219a808884996db67",
        name="GPv2AllowListAuthentication",
        api_key=api_key,
    )
    weth = boa.from_etherscan(
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", name="WETH9", api_key=api_key
    )
    boa.from_etherscan(
        "0xc92e8bdf79f0507f65a392b0ab4667716bfe0110",
        name="GPv2VaultRelayer",
        api_key=api_key,
    )

    sender = "0x0DdcB0769a3591230cAa80F85469240b71442089"

    weth_balance = weth.balanceOf(sender)
    assert weth_balance > 7027378344680119359698

    ether = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    settlement.settle(
        tokens=[cvg.address, ether, ether, cvg.address, ether],  # address[]
        clearingPrices=[  # uint256[]
            386907945258610235,
            7027378344680119359698,
            7027378344680119359698,
            386907945258610235,
            7047211565463415361062,
        ],
        # (uint256,uint256,address,uint256,uint256,uint32,bytes32,uint256,uint256,uint256,bytes)[]
        trades=[
            (
                3,
                4,
                "0x6ce49a4e52d081e480ecef87db009e12a4799c96",
                7047211565463415361062,
                385155419953981193,
                1718523259,
                to_bytes(
                    "0xe4517e636d7dd7d91fb84d77f3ec728f828995a990541a837d5d3a5ecba75d8a"
                ),
                0,
                0,
                7047211565463415361062,
                to_bytes(
                    "0x4cf1892377f3826e1fc54669003063ef523a92fec353774ed3bcf14d24a74795"
                    "1250fe68290e411fb919a740aceec258c78d9cb078abe2b13b9a51cd4bd377e91b"
                ),
            )
        ],
        interactions=(  # (address,uint256,bytes)[][3]
            [],
            [
                (
                    twocrypto.address,
                    0,
                    twocrypto.exchange.prepare_calldata(
                        to_int(
                            "0000000000000000000000000000000000000000000000000000000000000000"
                        ),
                        to_int(
                            "0100000000000000000000000000000000000000000000000000000000000000"
                        ),
                        to_int(
                            "00000000000000000000000000000000000000000000017cf4772bd7231858d2"
                        ),
                        to_int(
                            "000000000000000000000000000000000000000000000000055e92b9edea6e3b"
                        ),
                    ),
                ),
                (
                    weth.address,
                    0,
                    weth.withdraw.prepare_calldata(
                        to_int(
                            "000000000000000000000000000000000000000000000000055e92b9edea6e3b"
                        )
                    ),
                ),
            ],
            [],
        ),
        sender=sender,
        gas=585030,
    )

    trace = settlement.call_trace()
    trace.export_html("trace.html")

    trace_dict = trace.to_dict()
    assert trace_dict["address"] == settlement.address
    assert len(trace_dict["children"]) == 6
    assert trace_dict["children"][3]["text"] == (
        '[12862] WETH9.transfer(dst = "0x9008D19f58AAbD9eD0D60971565AA8510560ab41",'
        " wad = 386907983949408760) => (True)"
    )
