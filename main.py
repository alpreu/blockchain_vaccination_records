"""This file is for playing around. Feel free to alter it."""

from blockchain.block import *
from blockchain.chain import Chain
from blockchain.full_client import FullClient
from blockchain.transaction import *
from Crypto.PublicKey import RSA
import requests
import logging


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format="[ %(asctime)s ] %(levelname)-7s %(name)-s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    logger = logging.getLogger("blockchain")

    neighbors_list = os.getenv('NEIGHBORS_HOST_PORT')
    neighbors_list = map(str.strip, neighbors_list.split(","))
    nodes = ["http://" + neighbor for neighbor in neighbors_list]

    response = requests.get(nodes[0] + '/latest_block')

    content = response.text

    block = Block(content)


    logger.info("Block index is:" + str(block.index))
    logger.info("Block hash is:" + block.hash)

    with open("tests" + os.sep + "testkey_pub.bin", "rb") as public_key, open("tests" + os.sep + "testkey_priv.bin", "rb") as private_key:
        PUBLIC_KEY = RSA.import_key(public_key.read())
        PRIVATE_KEY = RSA.import_key(private_key.read())
    new_transaction = VaccineTransaction("a vaccine", PUBLIC_KEY).sign(PRIVATE_KEY)
    requests.post(nodes[0] + '/new_transaction', data=repr(new_transaction))

    full_client = FullClient()
    full_client.synchronize_blockchain()



def blocks():
    with open("tests" + os.sep + "testkey_pub.bin", "rb") as public_key, open("tests" + os.sep + "testkey_priv.bin", "rb") as private_key:
        PUBLIC_KEY = RSA.import_key(public_key.read())
        PRIVATE_KEY = RSA.import_key(private_key.read())

    # Create chain, already contains empty genesis
    chain = Chain()

    # new Block with transactions
    new_block = Block(chain.last_block().get_block_information())
    new_transaction = VaccineTransaction("a vaccine", PUBLIC_KEY).sign(PRIVATE_KEY)
    new_block.add_transaction(new_transaction)
    new_transaction = PermissionTransaction(Permission.doctor, PUBLIC_KEY).sign(PRIVATE_KEY)
    new_block.add_transaction(new_transaction)

    new_block.update_hash()
    new_block.persist()

    # read file from disk
    blockchain_folder = "blockchain"
    persistence_folder = os.path.join(blockchain_folder,
                                      CONFIG["persistance_folder"])
    with open(os.path.join(persistence_folder, "1"), "r") as file:
        recreated_block = Block(file.read())

    print(chain.find_block_by_index(0))
    print(new_block)
    print(recreated_block)

    # can build new block based on recreated block
    Block(recreated_block.get_block_information())