import logging


def IrokoLogger(name, fname="iroko"):
    logging.basicConfig()
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fhan = logging.FileHandler(fname)
    fhan.setLevel(logging.INFO)
    logger.addHandler(fhan)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fhan.setFormatter(formatter)
    return logger
