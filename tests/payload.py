PAYLOAD_TEMPLATE = "TLAB|{tunnel}|SESSION={session}|SEQ={seq}"

def make(tunnel, session, seq):
    return PAYLOAD_TEMPLATE.format(tunnel=tunnel, session=session, seq=seq)