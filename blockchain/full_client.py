import logging
import os
import random
import threading
import requests
import sched
import time

from .transaction_set import TransactionSet
from .block import Block
from .chain import Chain
from .judgement import Judgement
from .config import CONFIG
from .network.network import Network
from .transaction import *
from .helper.cryptography import generate_keypair
from Crypto.PublicKey import RSA

logger = logging.getLogger("client")
scheduler = sched.scheduler(time.time, time.sleep)


class FullClient(object):
    """docstring for FullClient"""
    def __init__(self):
        # Mock nodes by hard coding
        if os.getenv('NEIGHBORS_HOST_PORT'):
            neighbors_list = os.getenv('NEIGHBORS_HOST_PORT')
            neighbors_list = map(str.strip, neighbors_list.split(","))
            self.nodes = ["http://" + neighbor for neighbor in neighbors_list]
        else:
            self.nodes = ["http://127.0.0.1:9000"]
        self._setup_public_key()

        self.chain = Chain()
        self.transaction_set = TransactionSet()
        self.invalid_transactions = set()
        self.creator_election_thread = None
        self._start_election_thread()
        # Call this after starting the server.
        # self.synchronize_blockchain()
        # if os.getenv('REGISTER_AS_ADMISSION') == '1':
        #     self.register_self_as_admission()

        logger.debug("Finished full_client init.")
        logger.debug("My public key is: {} or {}".format(self.public_key,
                                                         self.public_key.hex()))

    def _start_election_thread(self):
        self.creator_election_thread = threading.Thread(target=self.creator_election, name="election thread", daemon=True)
        self.creator_election_thread.start()

    def determine_block_creation_node(self, timestamp=None):
        """Determine which admission node has to create the next block in chain for each branch.

        The method takes a timestamp as argument representing the time to for which to determine who should generate the
        next block. Defaults to 'now', which means "Who should create a block right now?"
        Returns a list of tuples (hash, public key) of the determined creator for each branch whose leaf is hash.

        If even the youngest creator failed to create a block within time, the method continues with the
        oldest submission node.
        """
        if not timestamp:
            timestamp = time.time()

        result = []
        for hash, admissions in self.chain.get_admissions():
            number_of_admissions = len(admissions)
            creator_history = self.chain.get_block_creation_history_by_hash(number_of_admissions, hash)

            last_block_timestamp = self.chain.find_block_by_hash(hash).timestamp

            delta_time = int(timestamp) - int(last_block_timestamp)

            nth_oldest_block = int(delta_time / CONFIG["block_time"])
            result.append((hash, creator_history[nth_oldest_block % number_of_admissions]))

        return result

    def _is_block_created_by_expected_creator(self, block):
        """Determine which admission node should be the creator of a given block.

        The method takes a block as argument representing the the block whose legitimate creator
        should be determined.

        If even the youngest creator failed to create a block within time, the method continues with the
        oldest submission node.

        Returns True if the block is created by the correct creator
        """
        logger.debug("Asking for block with hash {}".format(block.previous_block))
        parent_block = self.chain.find_block_by_hash(block.previous_block)
        admissions, _, _ = self.chain.get_registration_caches_by_blockhash(block.previous_block)
        number_of_admissions = len(admissions)
        creator_history = self.chain.get_block_creation_history_by_hash(number_of_admissions, block.previous_block)

        delta_time = int(block.timestamp) - int(parent_block.timestamp)
        nth_oldest_block = int(delta_time / CONFIG["block_time"])

        return creator_history[nth_oldest_block % number_of_admissions] == block.public_key

    def _setup_public_key(self):
        """Create new key pair if necessary.

        Create a public/private key pair on setup and save them in files. If
        the full client restarts, file will be read in.
        """
        key_folder = CONFIG["key_folder"]
        if not os.path.isdir(key_folder) or os.listdir(key_folder) == []:
            # No keys present, so generate new pair
            os.makedirs(CONFIG["key_folder"], exist_ok=True)

            logger.info("Generating new public/private key pair")
            self.public_key, self.private_key = generate_keypair()

            path = os.path.join(key_folder, CONFIG["key_file_names"][0])
            with open(path, "wb") as key_file:
                key_file.write(self.public_key.exportKey())

            path = os.path.join(key_folder, CONFIG["key_file_names"][1])
            with open(path, "wb") as key_file:
                key_file.write(self.private_key.exportKey())

        elif set(os.listdir(key_folder)) != set(CONFIG["key_file_names"]):
            # One key is missing
            logger.error("Public or Private key are not existent!")
            assert os.listdir(key_folder) == CONFIG["key_file_names"]

        else:
            # Keys are present
            path = os.path.join(key_folder, CONFIG["key_file_names"][0])
            with open(path, "rb") as key_file:
                self.public_key = RSA.import_key(key_file.read())

            path = os.path.join(key_folder, CONFIG["key_file_names"][1])
            with open(path, "rb") as key_file:
                self.private_key = RSA.import_key(key_file.read())

        self.public_key = self.public_key.exportKey("DER")

    def synchronize_blockchain(self):
        block = self.chain.get_first_branching_block()
        for node in self.nodes:
            if Network.send_sync_request(node, repr(block)):
                logger.debug("Synchronize with: {}".format(node))
                return
        logger.debug("Couldn't synchronize chain. No neighbour answered")

        return

    def handle_sync_request(self, sender_host, block):
        sender_address = "http://" + sender_host + ":9000"
        block = Block(block)
        first_branch_block = self.chain.get_first_branching_block()
        if first_branch_block.index < block.index:
            block = first_branch_block
        if not self.chain.find_block_by_hash(block.hash):
            # received block is not part of chain. send complete chain to be save
            block = self.chain.find_blocks_by_index(0)
        blocks_to_sync = self.chain.get_tree_list_at_hash(block.hash)
        for block in blocks_to_sync:
            logger.debug("Resending Block: {}".format(block))
            Network.send_block(sender_address, repr(block))

            judgements = self.chain.get_judgements_for_blockhash(block.hash)
            for judgement in judgements:
                Network.send_judgement(sender_address, repr(judgement))

        dead_branch_judgements = self.chain.get_dead_branches_since_blockhash(block.hash)
        for judgement in dead_branch_judgements:
            Network.send_judgement(sender_address, repr(judgement))

    def create_next_block(self, parent_hash, timestamp):
        new_block = Block(self.chain.find_block_by_hash(parent_hash).get_block_information(),
                          self.public_key)
        new_block.timestamp = timestamp

        admissions, doctors, vaccines = self.chain.get_registration_caches_by_blockhash(parent_hash)
        for _ in range(CONFIG["block_size"]):
            transaction = self.transaction_set.pop()
            if transaction:
                if transaction.validate(admissions, doctors, vaccines):
                    new_block.add_transaction(transaction)
                else:
                    logger.debug("Adding Transaction not to next block (invalid): {}".format(transaction))
                    self.invalid_transactions.add(transaction)
            else:
                # Transaction set is empty
                break
        new_block.sign(self.private_key)
        new_block.update_hash()
        return new_block

    def submit_block(self, block):
        self.chain.add_block(block)
        block.persist()
        self._broadcast_new_block(block)

    def received_new_block(self, block_representation):
        """This method is called when receiving a new block.

        It will check if the block was received earlier. If not it will process
        and broadcast the block and adding it to the chain or dangling blocks.
        """
        try:
            new_block = Block(block_representation)
        except Exception as e:
            logger.error("Received new block but couldn't process:\
                         {} {}".format(repr(block_representation), e))
            return
        logger.debug("Received new block: {}".format(str(new_block)))

        with self.chain:
            if self.chain.find_block_by_hash(new_block.hash) or\
               self.chain.is_block_dangling(new_block):
                logger.debug("The received block is already part of chain or "
                             "a dangling block: {}".format(str(new_block)))
                return
            self._broadcast_new_block(new_block)
            self._process_new_block(new_block)

    def _process_new_block(self, new_block):
        parent_block = self.chain.find_block_by_hash(new_block.previous_block)
        if not parent_block:
            self.chain.add_dangling_block(new_block)
            logger.debug("Parent block of received block not yet received. Adding new block to dangling blocks: {}"
                         .format(str(new_block)))
            return

        if not self._is_block_created_by_expected_creator(new_block):
            logger.debug("Creator of received block doesn't match expected creator. Creating deny judgement: {}"
                         .format(str(new_block)))
            self._create_and_submit_judgement(new_block, False)
            return
        else:
            if not new_block.validate(parent_block):
                logger.debug("Received block is not valid. Creating deny judgement: {}"
                             .format(str(new_block)))
                self._create_and_submit_judgement(new_block, False)
                return
            else:
                new_block.persist()
                invalidated_blocks = self.chain.add_block(new_block)

                for block in invalidated_blocks:
                    self._create_and_submit_judgement(block, False)
                self._create_and_submit_judgement(new_block, True)
                self.transaction_set.discard_multiple(new_block.transactions)
                for block in self.chain.get_list_of_dangling_blocks():
                    self._process_new_block(block)

    def creator_election(self):
        """This method checks if this node needs to generate a new block.

        If it is the next creator it will generate a block and submit it to the chain."""
        logger.debug("Started Thread {}".format(threading.current_thread()))

        while True:
            try:
                time.sleep(CONFIG["block_time"] / 2) # block_time needs to be at least 2s
                admission = False
                for _, admissions in self.chain.get_admissions():
                    if self.public_key in admissions:
                        admission = True
                if not admission:
                    logger.debug("Currently no admission in any branch. Going to sleep.")
                    continue
                with self.chain:
                    timestamp = int(time.time())
                    next_creators_list = self.determine_block_creation_node(timestamp)

                    for hash, next_creator in next_creators_list:
                        if next_creator == self.public_key:
                            logger.debug("creator_election: next creator is self")
                            new_block = self.create_next_block(hash, timestamp)
                            if not new_block.validate(self.chain.find_block_by_hash(hash)):
                                logger.error("New generated block is not valid! {}".format(repr(new_block)))
                                self.transaction_set.add_multiple(self.new_block.transactions)
                                continue
                            self.submit_block(new_block)
                        else:
                            logger.debug("creator_election: next creator is other")
            except Exception:
                logger.exception("Exception in election thread:")

        logger.debug("Thread {} is dead.".format(threading.current_thread()))

    def _request_block_at_index(self, index, node):
        route = node + "/request_block/index/" + str(index)
        block = requests.get(route)
        return Block(block.text)

    def _broadcast_new_block(self, block):
        for node in self.nodes:
            Network.send_block(node, repr(block))

    def _get_status_from_different_node(self, node):
        random_node = random.choice(self.nodes)
        block = Network.request_latest_block(random_node)
        return Block(block.text)

    def _broadcast_new_judgement(self, judgement):
        for node in self.nodes:
            Network.send_judgement(node, repr(judgement))

    def handle_received_judgement(self, judgement):
        judgement_object = eval(judgement)
        if self.chain.update_judgements(judgement_object):
            self._broadcast_new_judgement(judgement_object)

    def handle_incoming_transaction(self, transaction):
        transaction_object = eval(transaction)
        self.handle_transaction(transaction_object, broadcast=False)

    def handle_transaction(self, transaction, broadcast=False):
        if broadcast:
            self._broadcast_new_transaction(transaction)
        if self.transaction_set.contains(transaction):
            return  # Transaction was already received
        admissions_at_leaf = self.chain.get_admissions()
        for admissions in admissions_at_leaf:
            if self.public_key not in admissions[1]:
                logger.debug("Received transaction but this node is no admission node. Quit...")
                return
            if self._check_if_transaction_in_chain(transaction):
                return
        self.transaction_set.add(transaction)

    def _check_if_transaction_in_chain(self, transaction):
        """Check if the transaction is already part of the chain.

        Checks the last |number of current admission nodes| blocks
        by comparing every transaction in the block to the new one.
        If the genesis block is reached the function stops advancing
        to the previous block and returns."""
        for hash, admissions in self.chain.get_admissions():
            number_of_blocks_to_check = len(admissions)
            blocks_checked = 0
            block_to_check = self.chain.find_block_by_hash(hash)
            while blocks_checked < number_of_blocks_to_check:
                for transaction_in_chain in block_to_check.transactions:
                    if transaction == transaction_in_chain:
                        return True
                if block_to_check.index == 0:
                    return False  # stop early after reaching the genesis block
                previous_block_hash = block_to_check.previous_block
                block_to_check = self.chain.find_block_by_hash(previous_block_hash)
                blocks_checked += 1
        return False

    def _broadcast_new_transaction(self, transaction):
        """Broadcast transaction to required number of admission nodes."""
        # TODO: send to admissions only
        for node in self.nodes:
            Network.broadcast_new_transaction(node, repr(transaction))

    def create_transaction(self):
        transaction_type = input("What kind of transaction should be created? (Vaccination/Vaccine/Permission)").lower()
        if transaction_type == "vaccination":
            vaccine = input("Which vaccine was given?").lower()
            doctor_pubkey = eval(input("Enter doctors public key"))
            patient_pubkey = eval(input("Enter patients public key"))
            transaction = VaccinationTransaction(doctor_pubkey, patient_pubkey, vaccine)
            print(transaction)
            sign_now = input("Sign transaction now? (Y/N)").lower()
            if sign_now == "y":
                doctor_privkey = eval(input("Enter doctors private key"))
                patient_privkey = eval(input("Enter patients private key"))
                transaction.sign(doctor_privkey, patient_privkey)
                print(transaction)
                self.handle_transaction(transaction, broadcast=True)
            elif sign_now == "n":
                print("Cannot broadcast unsigned transactions, aborting.")
            else:
                print("Invalid option {}, aborting.".format(sign_now))
        elif transaction_type == "vaccine":
            vaccine = input("Which vaccine should be registered?").lower()
            admission_pubkey = eval(input("Enter admissions public key"))
            transaction = VaccineTransaction(vaccine, admission_pubkey)
            print(transaction)
            sign_now = input("Sign transaction now? (Y/N)").lower()
            if sign_now == "y":
                admission_privkey = eval(input("Enter admission private key"))
                transaction.sign(admission_privkey)
                print(transaction)
                self._handle_transaction(transaction, broadcast=True)
            elif sign_now == "n":
                print("Cannot broadcast unsigned transactions, aborting.")
            else:
                print("Invalid option {}, aborting.".format(sign_now))
        elif transaction_type == "permission":
            permission_name = input("Which permission should be granted? (Patient/Doctor/Admission)").lower()
            permission = Permission[permission_name]
            sender_pubkey = eval(input("Enter sender public key"))
            transaction = PermissionTransaction(permission, sender_pubkey)
            print(transaction)
            sign_now = input("Sign transaction now? (Y/N)").lower()
            if sign_now == "y":
                sender_privkey = eval(input("Enter sender private key"))
                transaction.sign(sender_privkey)
                print(transaction)
                self.handle_transaction(transaction, broadcast=True)
            elif sign_now == "n":
                print("Cannot broadcast unsigned transactions, aborting.")
            else:
                print("Invalid option {}, aborting.".format(sign_now))
        else:
            print("Invalid option {}, aborting.".format(transaction_type))

    def process_dangling_blocks(self):
        raise DeprecationWarning("This method shouldn't be used anymore")

    def register_self_as_admission(self):
        admissions_at_leaf = self.chain.get_admissions()
        for admissions in admissions_at_leaf:
            if self.public_key in admissions[1]:
                logger.debug("Already admission node, don't need to register.")
                return
        logger.debug("Going to register as admission node.")
        tx = PermissionTransaction(Permission["admission"], self.public_key)
        tx.sign(self.private_key)
        self._broadcast_new_transaction(tx)

    def _create_and_submit_judgement(self, block, accepted):
        admissions, _, _ = self.chain.get_registration_caches_by_blockhash(block.previous_block)
        if self.public_key not in admissions:
            logger.debug("No admission in branch of block: {}".format(block))
            return
        judgement = Judgement(block.hash, accepted, self.public_key)
        judgement.sign(self.private_key)
        self.chain.update_judgements(judgement)
        self._broadcast_new_judgement(judgement)
