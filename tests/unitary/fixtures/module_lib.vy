# pragma version ~=0.4.0

@view
def throw():
    raise "Error with message"

def throw_dev_reason():
    raise # dev: some dev reason
