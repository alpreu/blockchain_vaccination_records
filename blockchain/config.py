import logging

CONFIG = {
    # Log level of the whole system
    "loglevel": logging.DEBUG,
    # Current version
    "version": "0.0.1",
    # Folder, where all blocks are written to disk
    "persistance_folder": "blockchain/blockchain_files",
    # Serialization properties
    "serializaton": {
        "separator": ",",
        "line_terminator": "\n"
    },
    # Maximum amount of transactions per block
    "block_size": 1024,
    # Create a block every n seconds
    "block_time": 5,
    # Folder to store public/private key of the client
    "key_folder": "blockchain/keys",
    # Names of key files
    "key_file_names": ["public_key.bin", "private_key.bin"],
    # Network routes
    "ROUTES": {
        "new_block": "/new_block",
        "block_by_index": "/request_block/index/<index>",
        "block_by_hash": "/request_block/hash/<hash>",
        "new_transaction": "/new_transaction",
        "latest_block": "/latest_block"
    }
}
