import json

from vyper.semantics.types import EventT
from vyper.semantics.types.function import ContractFunctionT

from boa.vyper.contract import ABIContractFactory


class ERCToken(ABIContractFactory):
    abi = []

    def __init__(self, token_name):
        functions = [
            ContractFunctionT.from_abi(i)
            for i in self.abi
            if i.get("type") == "function"
        ]

        events = [EventT.from_abi(i) for i in self.abi if i.get("type") == "event"]

        super().__init__(token_name, functions, events)

    @classmethod
    def at(cls, address):
        token_instance = cls(cls.__name__)
        return super(ERCToken, token_instance).at(address)


class ERC20(ERCToken):
    abi = json.loads(
        """
    [
        {
            "constant": true,
            "inputs": [],
            "name": "name",
            "outputs": [
                {
                    "name": "",
                    "type": "string"
                }
            ],
            "payable": false,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": false,
            "inputs": [
                {
                    "name": "_spender",
                    "type": "address"
                },
                {
                    "name": "_value",
                    "type": "uint256"
                }
            ],
            "name": "approve",
            "outputs": [
                {
                    "name": "",
                    "type": "bool"
                }
            ],
            "payable": false,
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "constant": true,
            "inputs": [],
            "name": "totalSupply",
            "outputs": [
                {
                    "name": "",
                    "type": "uint256"
                }
            ],
            "payable": false,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": false,
            "inputs": [
                {
                    "name": "_from",
                    "type": "address"
                },
                {
                    "name": "_to",
                    "type": "address"
                },
                {
                    "name": "_value",
                    "type": "uint256"
                }
            ],
            "name": "transferFrom",
            "outputs": [
                {
                    "name": "",
                    "type": "bool"
                }
            ],
            "payable": false,
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "constant": true,
            "inputs": [],
            "name": "decimals",
            "outputs": [
                {
                    "name": "",
                    "type": "uint8"
                }
            ],
            "payable": false,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": true,
            "inputs": [
                {
                    "name": "_owner",
                    "type": "address"
                }
            ],
            "name": "balanceOf",
            "outputs": [
                {
                    "name": "balance",
                    "type": "uint256"
                }
            ],
            "payable": false,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": true,
            "inputs": [],
            "name": "symbol",
            "outputs": [
                {
                    "name": "",
                    "type": "string"
                }
            ],
            "payable": false,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": false,
            "inputs": [
                {
                    "name": "_to",
                    "type": "address"
                },
                {
                    "name": "_value",
                    "type": "uint256"
                }
            ],
            "name": "transfer",
            "outputs": [
                {
                    "name": "",
                    "type": "bool"
                }
            ],
            "payable": false,
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "constant": true,
            "inputs": [
                {
                    "name": "_owner",
                    "type": "address"
                },
                {
                    "name": "_spender",
                    "type": "address"
                }
            ],
            "name": "allowance",
            "outputs": [
                {
                    "name": "",
                    "type": "uint256"
                }
            ],
            "payable": false,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "payable": true,
            "stateMutability": "payable",
            "type": "fallback"
        },
        {
            "anonymous": false,
            "inputs": [
                {
                    "indexed": true,
                    "name": "owner",
                    "type": "address"
                },
                {
                    "indexed": true,
                    "name": "spender",
                    "type": "address"
                },
                {
                    "indexed": false,
                    "name": "value",
                    "type": "uint256"
                }
            ],
            "name": "Approval",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
                {
                    "indexed": true,
                    "name": "_from",
                    "type": "address"
                },
                {
                    "indexed": true,
                    "name": "to",
                    "type": "address"
                },
                {
                    "indexed": false,
                    "name": "value",
                    "type": "uint256"
                }
            ],
            "name": "Transfer",
            "type": "event"
        }
    ]
    """
    )


class ERC721(ERCToken):
    abi = json.loads(
        """
    [
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "approved",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            }
            ],
            "name": "Approval",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "operator",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "bool",
                "name": "approved",
                "type": "bool"
            }
            ],
            "name": "ApprovalForAll",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            }
            ],
            "name": "Transfer",
            "type": "event"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            }
            ],
            "name": "approve",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "constant": true,
            "inputs": [],
            "name": "totalSupply",
            "outputs": [
            {
                "name": "",
                "type": "uint256"
            }
            ],
            "payable": false,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            }
            ],
            "name": "balanceOf",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "balance",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            }
            ],
            "name": "getApproved",
            "outputs": [
            {
                "internalType": "address",
                "name": "operator",
                "type": "address"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "operator",
                "type": "address"
            }
            ],
            "name": "isApprovedForAll",
            "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "name",
            "outputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            }
            ],
            "name": "ownerOf",
            "outputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            }
            ],
            "name": "safeTransferFrom",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            },
            {
                "internalType": "bytes",
                "name": "data",
                "type": "bytes"
            }
            ],
            "name": "safeTransferFrom",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "operator",
                "type": "address"
            },
            {
                "internalType": "bool",
                "name": "_approved",
                "type": "bool"
            }
            ],
            "name": "setApprovalForAll",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "bytes4",
                "name": "interfaceId",
                "type": "bytes4"
            }
            ],
            "name": "supportsInterface",
            "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "symbol",
            "outputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            }
            ],
            "name": "tokenURI",
            "outputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "tokenId",
                "type": "uint256"
            }
            ],
            "name": "transferFrom",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]
    """
    )


class ERC1155(ERCToken):
    abi = json.loads(
        """
    [
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "account",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "operator",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "bool",
                "name": "approved",
                "type": "bool"
            }
            ],
            "name": "ApprovalForAll",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "operator",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "uint256[]",
                "name": "ids",
                "type": "uint256[]"
            },
            {
                "indexed": false,
                "internalType": "uint256[]",
                "name": "values",
                "type": "uint256[]"
            }
            ],
            "name": "TransferBatch",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "operator",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "id",
                "type": "uint256"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "value",
                "type": "uint256"
            }
            ],
            "name": "TransferSingle",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": false,
                "internalType": "string",
                "name": "value",
                "type": "string"
            },
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "id",
                "type": "uint256"
            }
            ],
            "name": "URI",
            "type": "event"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "account",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "id",
                "type": "uint256"
            }
            ],
            "name": "balanceOf",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address[]",
                "name": "accounts",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "ids",
                "type": "uint256[]"
            }
            ],
            "name": "balanceOfBatch",
            "outputs": [
            {
                "internalType": "uint256[]",
                "name": "",
                "type": "uint256[]"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "account",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "operator",
                "type": "address"
            }
            ],
            "name": "isApprovedForAll",
            "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256[]",
                "name": "ids",
                "type": "uint256[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "bytes",
                "name": "data",
                "type": "bytes"
            }
            ],
            "name": "safeBatchTransferFrom",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "id",
                "type": "uint256"
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            },
            {
                "internalType": "bytes",
                "name": "data",
                "type": "bytes"
            }
            ],
            "name": "safeTransferFrom",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "operator",
                "type": "address"
            },
            {
                "internalType": "bool",
                "name": "approved",
                "type": "bool"
            }
            ],
            "name": "setApprovalForAll",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "bytes4",
                "name": "interfaceId",
                "type": "bytes4"
            }
            ],
            "name": "supportsInterface",
            "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "id",
                "type": "uint256"
            }
            ],
            "name": "uri",
            "outputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    """
    )


class ERC4626(ERCToken):
    abi = json.loads(
        """
    [
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "spender",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "value",
                "type": "uint256"
            }
            ],
            "name": "Approval",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "sender",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "name": "Deposit",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "value",
                "type": "uint256"
            }
            ],
            "name": "Transfer",
            "type": "event"
        },
        {
            "anonymous": false,
            "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "sender",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "name": "Withdraw",
            "type": "event"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "spender",
                "type": "address"
            }
            ],
            "name": "allowance",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "spender",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            }
            ],
            "name": "approve",
            "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "asset",
            "outputs": [
            {
                "internalType": "address",
                "name": "assetTokenAddress",
                "type": "address"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "account",
                "type": "address"
            }
            ],
            "name": "balanceOf",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "name": "convertToAssets",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            }
            ],
            "name": "convertToShares",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [
            {
                "internalType": "uint8",
                "name": "",
                "type": "uint8"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            },
            {
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            }
            ],
            "name": "deposit",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            }
            ],
            "name": "maxDeposit",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "maxAssets",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            }
            ],
            "name": "maxMint",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "maxShares",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            }
            ],
            "name": "maxRedeem",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "maxShares",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            }
            ],
            "name": "maxWithdraw",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "maxAssets",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            },
            {
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            }
            ],
            "name": "mint",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            }
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "name",
            "outputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            }
            ],
            "name": "previewDeposit",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "name": "previewMint",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "name": "previewRedeem",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            }
            ],
            "name": "previewWithdraw",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            },
            {
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            }
            ],
            "name": "redeem",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            }
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "symbol",
            "outputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "totalAssets",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "totalManagedAssets",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "totalSupply",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            }
            ],
            "name": "transfer",
            "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            }
            ],
            "name": "transferFrom",
            "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "internalType": "uint256",
                "name": "assets",
                "type": "uint256"
            },
            {
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            }
            ],
            "name": "withdraw",
            "outputs": [
            {
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256"
            }
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]
    """
    )
