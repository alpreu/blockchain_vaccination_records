import logging
from blockchain.transaction.transaction import TransactionBase
import blockchain.helper.cryptography as crypto
import blockchain.helper.key_utils as key_utils
import sys

logger = logging.getLogger("blockchain")


class VaccinationTransaction(TransactionBase):
    """This class depicts a vaccination of a patient."""

    def __init__(self, doctor_pub_key, patient_pub_key, vaccine, doctor_signature=None, patient_signature=None, **kwargs):
        super(VaccinationTransaction, self).__init__(
            vaccine=vaccine, doctor_signature=doctor_signature, patient_signature=patient_signature, **kwargs
        )

        del self.signature  # remove the base classes single signature
        del self.sender_pubkey  # remove the base classes sender signature

        self.vaccine = vaccine
        self.doctor_signature = doctor_signature
        self.patient_signature = patient_signature
        self.doctor_pub_key = key_utils.cast_to_bytes(doctor_pub_key)
        self.patient_pub_key = key_utils.cast_to_bytes(patient_pub_key)

    def sign(self, doctor_private_key, patient_private_key):
        """create signatures and add it to the transaction.

        Each patient and doctor will sign.

        WONTFIX: Finally the patient privatekey should be given by the patient. More precisely, the key shouldn't even leave the patient's device.
        """
        self.doctor_signature = self._create_doctor_signature(doctor_private_key)
        self.patient_signature = self._create_patient_signature(patient_private_key)
        return self

    def validate(self, admissions, doctors, vaccines):
        """Validate the existing signatures.

        Check if the transaction fulfills the requirements
        WONTFIX: won't implement checking if patient is registered in presentation demo
        """
        if self.vaccine not in vaccines:
            logger.debug("vaccine is not registered.")
            self.validation_text = "vaccine is not registered."
            return False
        if self.doctor_pub_key not in doctors:
            logger.debug("doctor is not registered.")
            self.validation_text = "doctor is not registered."
            return False

        if not self.doctor_signature or not self.patient_signature:
            return False

        bin_doctor_key = key_utils.bytes_to_rsa(self.doctor_pub_key)
        doctor_signature = self._verify_doctor_signature(bin_doctor_key)
        if not doctor_signature:
            logger.debug("doctor signature is not valid")
            self.validation_text = "doctor signature is not valid"
            return False

        bin_patient_key = key_utils.bytes_to_rsa(self.patient_pub_key)
        patient_signature = self._verify_patient_signature(bin_patient_key)
        if not patient_signature:
            logger.debug("patient signature is not valid")
            self.validation_text = "patient signature is not valid"
            return False

        self.validation_text = "valid"
        return True

    def _create_doctor_signature(self, private_key):
        if self.doctor_signature:
            logger.debug("Doctor signature exists. Quit signing process.")
            return
        message = crypto.get_bytes(self._get_information_for_hashing(True))
        return crypto.sign(message, private_key)

    def _create_patient_signature(self, private_key):
        if self.patient_signature:
            logger.debug("Patient signature exists. Quit signing process.")
            return

        print(str(self))
        print("Patient, do you want to sign the vaccination? (Y/N): ")
        reply = sys.stdin.read(1)
        reply = str(reply).lower()

        if reply == "n":
            print("Aborting...")
            return None
        elif reply == "y":
            message = crypto.get_bytes(self._get_information_for_hashing(False))
            return crypto.sign(message, private_key)
        else:
            print("No valid input. Abort...")
            return None

    def _verify_doctor_signature(self, pub_key):
        message = crypto.get_bytes(self._get_information_for_hashing(True))
        return crypto.verify(message, self.doctor_signature, pub_key)

    def _verify_patient_signature(self, pub_key):
        message = crypto.get_bytes(self._get_information_for_hashing(False))
        return crypto.verify(message, self.patient_signature, pub_key)

    def _get_information_for_hashing(self, as_doctor):
        string = "{}(version={}, timestamp={}, vaccine={}, doctor_pub_key={}, patient_pub_key={}".format(
            type(self).__name__,
            self.version,
            self.timestamp,
            self.vaccine,
            self.doctor_pub_key,
            self.patient_pub_key
        )
        if not as_doctor:
            string = string + ", doctor_signature={}".format(self.doctor_signature)

        string = string + ")"

        return string
