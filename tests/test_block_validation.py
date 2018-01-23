from Crypto.PublicKey import RSA
import pytest
import os

from blockchain.block import Block, create_initial_block
from blockchain.transaction import *
from blockchain.block_validator import validate


PUBLIC_KEY = RSA.import_key(open("tests" + os.sep + "testkey_pub.bin", "rb").read())
PRIVATE_KEY = RSA.import_key(open("tests" + os.sep + "testkey_priv.bin", "rb").read())


@pytest.fixture()
def genesis():
    genesis = create_initial_block(PUBLIC_KEY)
    yield genesis


@pytest.fixture()
def block(genesis):
    new_block = Block(genesis.get_block_information(), PUBLIC_KEY)
    new_transaction = VaccineTransaction("a vaccine", PUBLIC_KEY).sign(PRIVATE_KEY)
    new_block.add_transaction(new_transaction)
    new_transaction = PermissionTransaction(Permission.doctor, PUBLIC_KEY).sign(PRIVATE_KEY)
    new_block.add_transaction(new_transaction)
    new_block.update_hash()
    yield new_block


def test_initial_block_is_valid(block, genesis):
    error = validate(block, genesis)
    assert error is None, "Error in initial block"


def test_index(block, genesis):
    block.index = 2000
    error = validate(block, genesis)
    assert error is not None, "Did not detect wrong index"
    assert "Wrong index" in error


def test_previous_block_hash(block, genesis):
    block.previous_block = "some random hash"
    error = validate(block, genesis)
    assert error is not None, "Did not detect wrong prev. block hash"
    assert "does not reference previous" in error


def test_version(block, genesis):
    block.version = 0
    error = validate(block, genesis)
    assert error is not None, "Did not detect wrong version"
    assert "Different versions" in error
