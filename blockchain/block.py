"""This module implements block functionality.

The block class provides necessary methods for block creation and
serialization. Furthermore, the creation of the genesis block is
implemented here.
Block validation is not and will not be implemented in here.
"""

import logging
import os
import shutil
from hashlib import sha256
from time import time

from blockchain.config import CONFIG
from blockchain.transaction import *
import blockchain.helper.cryptography as crypto
import blockchain.helper.key_utils as key_utils
from blockchain.helper.cryptography import generate_keypair
from blockchain.helper.logger import setup_basic_logger_config

logger = logging.getLogger("blockchain")


class Block(object):
    """This class represents a block in the blockchain."""

    def __init__(self, data, public_key=None):
        """Create or Recreate a block object.

        This constructor supports both, recreating a block by its string
        representation and creating a successor block based on the header
        information (type(data): dict) of the latest block.
        To create the successor block, the passed dictionary has to have
        the following fields:
        {
            "index": 0,         [index of the previous block]
            "hash": "166AD84E"  [hash of the previous block]
        }
        """
        if type(data) == dict:
            self._from_dictionary(data)
            assert public_key
            self.public_key = key_utils.cast_to_bytes(public_key)
            self.signature = ""
        elif type(data) == str:
            self._from_string(data)
        else:
            raise ValueError("Given argument is neither string nor dict!")

    def _from_string(self, data):
        """Recreate a block by its string representation.

        Recreate a block object based on a given string representation
        of a block. This will create a new object with the same attributes.
        """
        fields = ["index",
                  "previous_block",
                  "version",
                  "timestamp",
                  "public_key",
                  "signature",
                  "hash"]
        header, transactions = data.split(
            CONFIG.serializaton["line_terminator"], 1)
        header_content = header.split(CONFIG.serializaton["separator"])
        header_information = dict(zip(fields, header_content))
        assert len(fields) == len(header_information), "Wrong header format!"
        self.index = int(header_information["index"])
        self.previous_block = header_information["previous_block"]
        self.version = header_information["version"]
        self.timestamp = int(header_information["timestamp"])
        self.public_key = key_utils.hex_to_bytes(header_information["public_key"])
        self.signature = header_information["signature"]
        # Block ends with \n. Thus, splitting by line terminator will create
        # an empty string. We have to ignore this at this point.
        transaction_list = transactions.split(
            CONFIG.serializaton["line_terminator"])[:-1]
        self.transactions = [eval(tx) for tx in transaction_list]
        self.hash = header_information["hash"]

    def _from_dictionary(self, data):
        """Create a successor block based on header information."""
        logger.debug("Creating new block")
        self.index = int(data["index"]) + 1
        self.previous_block = data["hash"]
        self.version = CONFIG.version
        self.timestamp = int(time())
        self.transactions = []
        self.hash = ""

    def add_transaction(self, transaction):
        self.transactions.append(transaction)

    def get_block_information(self):
        """Return the necessary information for creating a new block."""
        return {
            "index": self.index,
            "hash": self.hash
        }

    def update_hash(self):
        """Add hash to the final state of the block."""
        sha = sha256()
        sha.update(self.get_content_for_hashing().encode("utf-8"))
        self.hash = sha.hexdigest()
        logger.debug("Finished creation of block:\n{}".format(str(self)))

    def get_content_for_hashing(self):
        """Return relevant block information for hashing."""
        fields = [str(self.index),
                  self.previous_block,
                  self.version,
                  str(self.timestamp),
                  key_utils.bytes_to_hex(self.public_key),
                  self.signature]
        content = CONFIG.serializaton["separator"].join(fields)
        content += CONFIG.serializaton["line_terminator"]
        for transaction in self.transactions:
            content += repr(transaction) + CONFIG.serializaton["line_terminator"]
        return content

    def persist(self):
        """Write the block into a file for persistency."""
        persistence_folder = CONFIG.persistance_folder
        os.makedirs(persistence_folder, exist_ok=True)
        file_name = "_".join([str(self.index), self.previous_block, self.hash])
        file_path = os.path.join(persistence_folder, file_name)
        with open(file_path, "w") as block_file:
            block_file.write(repr(self))
        logger.debug("Block {} written to disk: {}".format(self.index, str(self)))

    def validate(self, previous_block):
        """Validate block based on defined rules."""
        return validate_block(self, previous_block)

    def sign(self, private_key):
        """Sign creator's public key, in order to prove identity."""
        block_content = str.encode(self._get_content_for_signing())
        self.signature = key_utils.bytes_to_hex(crypto.sign(block_content, private_key))

    def _get_content_for_signing(self):
        """Return relevant block information for signing.

        This method is needed at two points:
        1. Signing of a block
        2. Validating a block's signature
        In both scenarios, we need the block representation without
        its signature and hash.
        """
        fields = [str(self.index),
                  self.previous_block,
                  self.version,
                  str(self.timestamp),
                  key_utils.bytes_to_hex(self.public_key)]

        content = CONFIG.serializaton["separator"].join(fields)
        content += CONFIG.serializaton["line_terminator"]

        for transaction in self.transactions:
            content += repr(transaction) + CONFIG.serializaton["line_terminator"]
        return content

    def __eq__(self, other):
        return self.hash == other.hash

    def __hash__(self):
        return hash(self.hash)

    def __repr__(self):
        """Create a string representation of the current block for hashing."""
        fields = [str(self.index),
                  self.previous_block,
                  self.version,
                  str(self.timestamp),
                  key_utils.bytes_to_hex(self.public_key)]
        if self.signature != "":
            fields.append(self.signature)
        if self.hash != "":
            fields.append(self.hash)
        block = CONFIG.serializaton["separator"].join(fields)
        block += CONFIG.serializaton["line_terminator"]
        for transaction in self.transactions:
            block += repr(transaction) + CONFIG.serializaton["line_terminator"]
        return block

    def __str__(self):
        return ("\n=======================\n"
                "  Block {}\n"
                "  Previous block: {}\n"
                "  Number of transactions: {}\n"
                "  Public key: {}\n"
                "  hash: {}\n"
                "=======================").format(self.index,
                                                  self.previous_block,
                                                  len(self.transactions),
                                                  self.public_key,
                                                  self.hash)


def create_initial_block():
    """Create a new genesis block."""
    setup_basic_logger_config()
    logger.info("Creating new keypair for genesis block.")
    public_key, private_key = generate_keypair()

    key_folder = CONFIG.key_folder
    os.makedirs(CONFIG.key_folder, exist_ok=True)

    path = os.path.join(key_folder, CONFIG.key_file_names[0])
    key_utils.write_key_to_pem(public_key, path)

    path = os.path.join(key_folder, CONFIG.key_file_names[1])
    key_utils.write_key_to_pem(private_key, path)

    if os.path.exists(CONFIG.persistance_folder):
        shutil.rmtree(CONFIG.persistance_folder)
        os.makedirs(CONFIG.persistance_folder)

    logger.info("Creating new genesis block")
    genesis = Block({
        "index": -1,  # index is always incremented by one, so genesis index is actually 0
        "hash": str(0)
    }, public_key)
    initial_admission_tx = PermissionTransaction(
        Permission.admission,
        public_key).sign(private_key)
    genesis.add_transaction(initial_admission_tx)
    genesis.sign(private_key)
    genesis.update_hash()
    genesis.persist()
    return genesis


from .helper.block_validator import validate_block
