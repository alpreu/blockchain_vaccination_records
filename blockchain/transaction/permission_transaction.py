import logging
import blockchain.helper.cryptography as crypto
from Crypto.PublicKey import RSA
from time import time
from enum import Enum
from blockchain.transaction.transaction import TransactionBase

from blockchain.config import CONFIG
from blockchain.helper.cryptography import hexify

# Needs to be moved later
logging.basicConfig(level=logging.DEBUG,
                    format='[ %(asctime)s ] %(levelname)-7s %(name)-s: %(message)s',
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger('blockchain')


class Permission(Enum):
    patient = "patient"
    admission = "admission"
    doctor = "doctor"

# TODO The Constructor should be able to load a complete transaction (see __repr__ of base class)
class PermissionTransaction(TransactionBase):
    def __init__(self, requested_permission, sender_pubkey):
        super(PermissionTransaction, self).__init__()
        logger.debug('Creating new permission transaction')
        self.requested_permission = requested_permission
        self.sender_pubkey = sender_pubkey.exportKey("DER")
        self.signature = None

    def get_transaction_information(self):
        return {
            'version': self.version,
            'timestamp': self.timestamp,
            'requested_permission': self.requested_permission,
            'sender_wallet': self.sender_pubkey,
            'signature': self.signature
        }

    def _get_informations_for_hashing(self):
        return {
            'version': self.version,
            'timestamp': self.timestamp,
            'requested_permission': self.requested_permission.name,
            'sender_wallet': self.sender_pubkey
        }

    def validate(self):
        """
        checks if the transaction fulfills the requirements
        e.g. if enough positive votes were cast for an admission,
        signature matches, etc.
        """
        return self._verify_signature() # TODO check other requirements

    def _verify_signature(self):
        message = crypto.get_bytes(str(self._get_informations_for_hashing()))
        return crypto.verify(message, self.signature, RSA.import_key(self.sender_pubkey))

    def _create_signature(self, private_key):
        message = crypto.get_bytes(str(self._get_informations_for_hashing()))
        return crypto.sign(message, private_key)

    def sign(self, private_key):
        """creates a signature and adds it to the transaction"""
        self.signature = self._create_signature(private_key)

