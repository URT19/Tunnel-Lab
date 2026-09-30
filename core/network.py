import ipaddress

class Allocator:
    def __init__(self, pool="10.250.0.0/16", prefix=30):
        self.pool = ipaddress.ip_network(pool)
        self.prefix = prefix
        self.index = 1

    def next_pair(self):
        subnets = self.pool.subnets(new_prefix=self.prefix)
        for i, net in enumerate(subnets):
            if i == self.index:
                self.index += 1
                hosts = list(net.hosts())
                return str(hosts[0]), str(hosts[1])
        raise RuntimeError("pool exhausted")