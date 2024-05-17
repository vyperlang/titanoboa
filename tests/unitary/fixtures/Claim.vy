# @version 0.3.10
# @dev Implementation of ERC-721 non-fungible token standard.
# @author ApeWorX Team (@ApeWorX), Ryuya Nakamura (@nrryuya), Vyperlang Contributors
# Modified from: https://github.com/vyperlang/vyper/blob/master/examples/tokens/ERC721.vy

from vyper.interfaces import ERC721

implements: ERC721

############ ERC-165 #############

# @dev Static list of supported ERC165 interface ids
# NOTE: update when `bytes4` is added
SUPPORTED_INTERFACES: constant(bytes4[5]) = [
    # ERC165 interface ID of ERC165
    0x01ffc9a7,
    # ERC165 interface ID of ERC721
    0x80ac58cd,
    # ERC165 interface ID of ERC721 Metadata extension
    0x5b5e139f,
    # ERC165 interface ID of ERC2981
    0x2a55205a,
    # ERC165 interface ID of ERC4494
    0x5604e225,
]

############ ERC-721 #############

# Interface for the contract called by safeTransferFrom()
interface ERC721Receiver:
    def onERC721Received(
            operator: address,
            owner: address,
            tokenId: uint256,
            data: Bytes[1024]
        ) -> bytes4: view

# @dev Emits when ownership of any NFT changes by any mechanism. This event emits when NFTs are
#      created (`from` == 0) and destroyed (`to` == 0). Exception: during contract creation, any
#      number of NFTs may be created and assigned without emitting Transfer. At the time of any
#      transfer, the approved address for that NFT (if any) is reset to none.
# @param _from Sender of NFT (if address is zero address it indicates token creation).
# @param _to Receiver of NFT (if address is zero address it indicates token destruction).
# @param _tokenId The NFT that got transfered.
event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    tokenId: indexed(uint256)

# @dev This emits when the approved address for an NFT is changed or reaffirmed. The zero
#      address indicates there is no approved address. When a Transfer event emits, this also
#      indicates that the approved address for that NFT (if any) is reset to none.
# @param _owner Owner of NFT.
# @param _approved Address that we are approving.
# @param _tokenId NFT which we are approving.
event Approval:
    owner: indexed(address)
    approved: indexed(address)
    tokenId: indexed(uint256)

# @dev This emits when an operator is enabled or disabled for an owner. The operator can manage
#      all NFTs of the owner.
# @param _owner Owner of NFT.
# @param _operator Address to which we are setting operator rights.
# @param _approved Status of operator rights(true if operator rights are given and false if
# revoked).
event ApprovalForAll:
    owner: indexed(address)
    operator: indexed(address)
    approved: bool


# @dev Base URI string used for all NFT's URI fields (modified by tokenId)
baseURI: public(String[56])

# @dev Number of tokens issued
totalSupply: public(uint256)

# @dev Cannot issue more than this number
MAX_TOTAL_SUPPLY: constant(uint256) = 1_000_000_000_000

# @dev Mapping from owner address to count of his tokens.
balanceOf: public(HashMap[address, uint256])

# @dev Mapping from NFT ID to the address that owns it.
ownerOf: public(HashMap[uint256, address])

# @dev Mapping from NFT ID to approved address.
idToApprovals: HashMap[uint256, address]

# @dev Mapping from owner address to mapping of operator addresses.
isApprovedForAll: public(HashMap[address, HashMap[address, bool]])

# @dev Set of addresses who can mint a token
is_minter: public(HashMap[address,bool])

# @dev Owner address who can call only owner functions
owner: public(address)

name: public(String[128])
symbol: public(String[128])
description: public(String[1024])

############ ERC-2981 ############

# NOTE: Makes `royaltyInfo` return type easier to read
struct RoyaltyInfo:
    receiver: address
    royaltyAmount: uint256

# @dev Artist that earns royalty payments
artist: public(address)

# @dev How much to give the artist in royalties (BPS, or x/10_000)
ROYALTY: constant(uint256) = 500

############ ERC-4494 ############

# @dev Mapping of TokenID to nonce values used for ERC4494 signature verification
nonces: public(HashMap[uint256, uint256])

# @dev EIP712 semi-immutable Domain Separator
# NOTE: can be updated only in case of `chain.id` hardfork per EIP-1134
DOMAIN_SEPARATOR: public(bytes32)

# @dev EIP712 TypeHash for ERC4494 permit message
EIP712_DOMAIN_TYPEHASH: constant(bytes32) = keccak256(
    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)

# @dev EIP712 VersionHash for ERC4494 permit message
EIP712_DOMAIN_VERSIONHASH: constant(bytes32) = keccak256("1.0")

@external
def __init__(baseURI: String[56], name: String[128], symbol: String[128], description: String[1024]):
    """
    @dev Contract constructor.
    """
    # ERC-721 functions
    self.owner = msg.sender
    self.baseURI = baseURI
    self.name = name
    self.symbol = symbol
    self.description = description

    # ERC712 domain separator for ERC4494
    self.DOMAIN_SEPARATOR = keccak256(
        _abi_encode(
            EIP712_DOMAIN_TYPEHASH,
            keccak256(self.name),
            EIP712_DOMAIN_VERSIONHASH,
            chain.id,
            self,
        )
    )

    self.is_minter[msg.sender] = True

@external
def setDomainSeparator():
    """
    @dev Update the domain separator in case of a hardfork where chain ID changes
    """
    self.DOMAIN_SEPARATOR = keccak256(
        _abi_encode(
            EIP712_DOMAIN_TYPEHASH,
            keccak256(self.name),
            EIP712_DOMAIN_VERSIONHASH,
            chain.id,
            self,
        )
    )

############ ERC-165 #############

@pure
@external
def supportsInterface(interface_id: bytes4) -> bool:
    """
    @dev Interface identification is specified in ERC-165.
    @param interface_id Id of the interface support required
    @return bool This contract does support the given interface
    """
    # NOTE: Not technically compliant
    return interface_id in SUPPORTED_INTERFACES

##### ERC-721 VIEW FUNCTIONS #####

@view
@external
def tokenURI(tokenId: uint256) -> String[140]:
    return concat(self.baseURI, "/", uint2str(tokenId), ".json")

@external
def updateBaseURI(baseURI: String[56]):
    assert msg.sender == self.owner
    self.baseURI = baseURI

@external
def updateOwner(owner:address):
    assert msg.sender == self.owner
    self.owner = owner

@view
@external
def getApproved(tokenId: uint256) -> address:
    """
    @dev Get the approved address for a single NFT.
         Throws if `tokenId` is not a valid NFT.
    @param tokenId ID of the NFT to query the approval of.
    """
    # Throws if `tokenId` is not a valid NFT
    assert self.ownerOf[tokenId] != empty(address)
    return self.idToApprovals[tokenId]

### TRANSFER FUNCTION HELPERS ###

@view
@internal
def _isApprovedOrOwner(spender: address, tokenId: uint256) -> bool:
    """
    Returns whether the msg.sender is approved for the given token ID,
        is an operator of the owner, or is the owner of the token
    """
    owner: address = self.ownerOf[tokenId]

    if owner == spender:
        return True

    if spender == self.idToApprovals[tokenId]:
        return True

    if (self.isApprovedForAll[owner])[spender]:
        return True

    return False

@internal
def _transferFrom(owner: address, receiver: address, tokenId: uint256, sender: address):
    """
    Exeute transfer of a NFT.
      Throws unless `msg.sender` is the current owner, an authorized operator, or the approved
      address for this NFT. (NOTE: `msg.sender` not allowed in private function so pass `sender`.)
      Throws if `receiver` is the zero address.
      Throws if `owner` is not the current owner.
      Throws if `tokenId` is not a valid NFT.
    """
    # Check requirements
    assert self._isApprovedOrOwner(sender, tokenId)
    assert receiver != empty(address)
    assert owner != empty(address)

    # Reset approvals, if any
    if self.idToApprovals[tokenId] != empty(address):
        self.idToApprovals[tokenId] = empty(address)

    # EIP-4494: increment nonce on transfer for safety
    self.nonces[tokenId] += 1

    # Change the owner
    self.ownerOf[tokenId] = receiver

    # Change count tracking
    self.balanceOf[owner] -= 1
    self.balanceOf[receiver] += 1

    # Log the transfer
    log Transfer(owner, receiver, tokenId)

### TRANSFER FUNCTIONS ###

@external
def transferFrom(owner: address, receiver: address, tokenId: uint256):
    """
    @dev Throws unless `msg.sender` is the current owner, an authorized operator, or the approved
         address for this NFT.
         Throws if `owner` is not the current owner.
         Throws if `receiver` is the zero address.
         Throws if `tokenId` is not a valid NFT.
    @notice The caller is responsible to confirm that `receiver` is capable of receiving NFTs or else
            they maybe be permanently lost.
    @param owner The current owner of the NFT.
    @param receiver The new owner.
    @param tokenId The NFT to transfer.
    """
    self._transferFrom(owner, receiver, tokenId, msg.sender)

@external
def safeTransferFrom(
        owner: address,
        receiver: address,
        tokenId: uint256,
        data: Bytes[1024]=b""
    ):
    """
    @dev Transfers the ownership of an NFT from one address to another address.
         Throws unless `msg.sender` is the current owner, an authorized operator, or the
         approved address for this NFT.
         Throws if `owner` is not the current owner.
         Throws if `receiver` is the zero address.
         Throws if `tokenId` is not a valid NFT.
         If `receiver` is a smart contract, it calls `onERC721Received` on `_to` and throws if
         the return value is not `bytes4(keccak256("onERC721Received(address,address,uint256,bytes)"))`.
         NOTE: bytes4 is represented by bytes32 with padding
    @param owner The current owner of the NFT.
    @param receiver The new owner.
    @param tokenId The NFT to transfer.
    @param data Additional data with no specified format, sent in call to `receiver`.
    """
    self._transferFrom(owner, receiver, tokenId, msg.sender)
    if receiver.is_contract: # check if `receiver` is a contract address capable of processing a callback
        returnValue: bytes4 = ERC721Receiver(receiver).onERC721Received(msg.sender, owner, tokenId, data)
        # Throws if transfer destination is a contract which does not implement 'onERC721Received'
        assert returnValue == method_id("onERC721Received(address,address,uint256,bytes)", output_type=bytes4)


##### APPROVAL FUNCTIONS #####

@external
def approve(approved: address, tokenId: uint256):
    """
    @dev Set or reaffirm the approved address for an NFT. The zero address indicates there is no approved address.
         Throws unless `msg.sender` is the current NFT owner, or an authorized operator of the current owner.
         Throws if `tokenId` is not a valid NFT. (NOTE: This is not written the EIP)
         Throws if `approved` is the current owner. (NOTE: This is not written the EIP)
    @param approved Address to be approved for the given NFT ID.
    @param tokenId ID of the token to be approved.
    """
    # Throws if `_tokenId` is not a valid NFT
    owner: address = self.ownerOf[tokenId]
    assert owner != empty(address)

    # Throws if `approved` is the current owner
    assert approved != owner

    # Throws if `msg.sender` is not the current owner, or is approved for all actions
    if not (
        owner == msg.sender
        or (self.isApprovedForAll[owner])[msg.sender]
    ):
       raise

    # Set the approval
    self.idToApprovals[tokenId] = approved
    log Approval(owner, approved, tokenId)

@external
def permit(spender: address, tokenId: uint256, deadline: uint256, sig: Bytes[65]) -> bool:
    """
    @dev Allow a 3rd party to approve a transfer via EIP-721 message
        Raises if permit has expired
        Raises if `tokenId` is unowned
        Raises if permit is not signed by token owner
        Raises if `nonce` is not the current expected value
        Raises if `sig` is not a supported signature type
    @param spender The approved spender of `tokenId` for the permit
    @param tokenId The token that is being approved
        NOTE: signer is checked against this token's owner
    @param deadline The time limit for which the message is valid for
    @param sig The signature for the message, either in vrs or EIP-2098 form
    @return bool If the operation is successful
    """
    # Permit is still valid
    assert block.timestamp <= deadline

    # Ensure the token is owned by someone
    owner: address = self.ownerOf[tokenId]
    assert owner != empty(address)

    # Nonce for given token (signer must ensure they use latest)
    nonce: uint256 = self.nonces[tokenId]

    # Compose EIP-712 message hash
    message: bytes32 = keccak256(
        _abi_encode(
            0x1901,
            self.DOMAIN_SEPARATOR,
            keccak256(
                _abi_encode(
                    keccak256(
                        "Permit(address spender,uint256 tokenId,uint256 nonce,uint256 deadline)"
                    ),
                    spender,
                    tokenId,
                    nonce,
                    deadline,
                )
            )
        )
    )

    # Validate signature
    v: uint256 = 0
    r: uint256 = 0
    s: uint256 = 0
    if len(sig) == 65:
        # Normal encoded VRS signatures
        v = convert(slice(sig, 0, 1), uint256)
        r = convert(slice(sig, 1, 32), uint256)
        s = convert(slice(sig, 33, 32), uint256)

    elif len(sig) == 64:
        # EIP-2098 compact signatures
        r = convert(slice(sig, 0, 32), uint256)
        v = convert(slice(sig, 33, 1), uint256)
        s = convert(slice(sig, 34, 31), uint256)

    else:
        raise  # Other schemes not supported

    assert ecrecover(message, v, r, s) == owner

    self.nonces[tokenId] = nonce + 1
    self.idToApprovals[tokenId] = spender

    return True

@external
def setApprovalForAll(operator: address, approved: bool):
    """
    @dev Enables or disables approval for a third party ("operator") to manage all of
         `msg.sender`'s assets. It also emits the ApprovalForAll event.
    @notice This works even if sender doesn't own any tokens at the time.
    @param operator Address to add to the set of authorized operators.
    @param approved True if the operators is approved, false to revoke approval.
    """
    self.isApprovedForAll[msg.sender][operator] = approved
    log ApprovalForAll(msg.sender, operator, approved)

### MINT FUNCTIONS ###

@external
def setMinter(minter: address):
    """
    @dev Function to change the minter
         Throws if `msg.sender` is not the minter.
    @param minter The address that will become the new minter
    """
    assert msg.sender == self.owner
    self.is_minter[minter] = True

@external
def mint(receiver: address) -> bool:
    """
    @dev Function to mint tokens
         Throws if `msg.sender` is not the minter.
         Throws if `receiver` is zero address.
         Throws if we've minted the whole supply
    @param receiver The address that will receive the minted tokens.
    @return A boolean that indicates if the operation was successful.
    """
    assert self.is_minter[msg.sender]

    # Throws if `receiver` is zero address
    assert receiver != empty(address)

    # Throws if we've minted the whole supply
    assert self.totalSupply < MAX_TOTAL_SUPPLY

    # Give the `receiver` their token
    tokenId: uint256 = convert(receiver, uint256)
    self.ownerOf[tokenId] = receiver
    self.balanceOf[receiver] += 1
    self.totalSupply += 1

    log Transfer(empty(address), receiver, tokenId)
    return True
