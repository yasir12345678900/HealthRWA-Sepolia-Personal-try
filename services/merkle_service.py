'''
Consent tree and revocation tree for HALAH (off-chain copy)
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11

The consent contract keeps two Merkle trees of depth 16 over the Poseidon hash (Chapter 7, Section 7.2.3):

    consent tree      leaf i is the commitment of the i-th issued consent (token i + 1). The contract
                      keeps the current root and the last 8 roots, so that a mint during proving
                      does not void a proof.
    revocation tree   leaf i is 0 while consent i is not revoked and 1 once it is revoked.

The contract stores the roots only. The prover needs the path of a leaf, so this module keeps the same
two trees off chain, fed with the same mints and revocations, and gives the paths that Algorithm 7.2
puts into the witness. Both trees can be built again from the ConsentIssued and ConsentRevoked events.

A node is Poseidon(left, right). An empty leaf is 0, and the root of an empty subtree of height h is
Z(0) = 0, Z(h + 1) = Poseidon(Z(h), Z(h)). Only the nodes that differ from these values are stored.

MerkleTree(depth)                     -> root, leaf(i), path(i)
ConsentTree(commitments)              -> append(c), index_of(c), recent_roots(), is_known_root(root)
RevocationTree(revoked)               -> revoke(i), is_revoked(i), path(i)
root_from_path(leaf, index, siblings) -> the root that a path leads to
'''
from services.commitment_service import field_element, poseidon

TREE_DEPTH = 16          # depth of both trees: 2^16 consents
RECENT_ROOTS = 8         # earlier consent roots that stay acceptable beside the current one


def empty_roots(depth=TREE_DEPTH):
    '''Roots of the empty subtrees: Z(0) .. Z(depth).'''
    zeros = [0]
    for _ in range(depth):
        zeros.append(poseidon([zeros[-1], zeros[-1]]))
    return zeros


def root_from_path(leaf, index, siblings):
    '''The root that a leaf at `index` reaches through its siblings, from the leaf level upwards.
    Bit h of the index says whether the node at height h is a right child.'''
    node = field_element(leaf)
    for height, sibling in enumerate(siblings):
        if (int(index) >> height) & 1:
            node = poseidon([sibling, node])
        else:
            node = poseidon([node, sibling])
    return node


class MerkleTree:
    '''Merkle tree of fixed depth over Poseidon. Only nodes that are not empty are stored.'''

    def __init__(self, depth=TREE_DEPTH, leaves=None):
        if not 1 <= int(depth) <= 32:
            raise ValueError("depth must lie between 1 and 32")
        self.depth = int(depth)
        self.capacity = 1 << self.depth
        self._zeros = empty_roots(self.depth)
        self._levels = [dict() for _ in range(self.depth + 1)]      # height -> {index: node}
        if leaves:
            self._load(leaves)

    def _load(self, leaves):
        '''Fill the tree from a list of leaves, level by level (one hash for every stored node).'''
        if len(leaves) > self.capacity:
            raise ValueError("more leaves than the tree holds")
        leaves = [field_element(leaf) for leaf in leaves]
        self._levels[0] = {i: leaf for i, leaf in enumerate(leaves) if leaf != 0}
        for height in range(self.depth):
            below = self._levels[height]
            self._levels[height + 1] = {
                parent: poseidon([self._node(height, 2 * parent), self._node(height, 2 * parent + 1)])
                for parent in {index >> 1 for index in below}}

    def _node(self, height, index):
        return self._levels[height].get(index, self._zeros[height])

    def _check_index(self, index):
        index = int(index)
        if not 0 <= index < self.capacity:
            raise IndexError("leaf index is outside the tree")
        return index

    def _set_leaf(self, index, value):
        '''Write one leaf and recompute the nodes on its path to the root.'''
        index = self._check_index(index)
        self._levels[0][index] = field_element(value)
        for height in range(self.depth):
            index >>= 1
            self._levels[height + 1][index] = poseidon(
                [self._node(height, 2 * index), self._node(height, 2 * index + 1)])

    @property
    def root(self):
        return self._node(self.depth, 0)

    def leaf(self, index):
        return self._node(0, self._check_index(index))

    def path(self, index):
        '''The opening of leaf `index`: the leaf, its siblings from the leaf level upwards, the bits
        of the index (1 = the node is a right child) and the root they lead to.'''
        index = self._check_index(index)
        siblings = [self._node(height, (index >> height) ^ 1) for height in range(self.depth)]
        return {"index": index, "leaf": self.leaf(index), "siblings": siblings,
                "bits": [(index >> height) & 1 for height in range(self.depth)], "root": self.root}


class ConsentTree(MerkleTree):
    '''The tree of the commitments of issued consents, in the order of their mint.'''

    def __init__(self, commitments=None, depth=TREE_DEPTH):
        super().__init__(depth)
        self.count = 0                                   # consents issued = index of the next free leaf
        self._index = {}                                 # commitment -> leaf index
        self._roots = [self.root]                        # the current root first, then the earlier ones
        commitments = [self._commitment(c) for c in (commitments or [])]
        # A long list is loaded in one pass. The last mints are replayed one by one, so that the
        # list of recent roots is the one the contract holds after the same mints.
        bulk = max(0, len(commitments) - RECENT_ROOTS)
        if bulk:
            if len(set(commitments[:bulk])) != bulk:
                raise ValueError("commitment already issued")
            self._load(commitments[:bulk])
            self._index = {c: i for i, c in enumerate(commitments[:bulk])}
            self.count = bulk
            self._roots = [self.root]
        for commitment in commitments[bulk:]:
            self.append(commitment)

    @staticmethod
    def _commitment(value):
        '''A commitment as an integer. Accepts an integer or a decimal or 0x string. A commitment
        is never 0, which is the value of an empty leaf.'''
        value = field_element(value)
        if value == 0:
            raise ValueError("a commitment is not zero")
        return value

    def append(self, commitment):
        '''Insert the commitment of a newly issued consent at the next free leaf (the mint of
        Algorithm 5.3) and return its leaf index. A commitment is issued once.'''
        commitment = self._commitment(commitment)
        if commitment in self._index:
            raise ValueError("commitment already issued")
        if self.count >= self.capacity:
            raise ValueError("consent tree is full")
        index = self.count
        self._set_leaf(index, commitment)
        self._index[commitment] = index
        self.count += 1
        self._roots = [self.root] + self._roots[:RECENT_ROOTS]
        return index

    def index_of(self, commitment):
        '''Leaf index of an issued commitment, or None when it was never issued.'''
        try:
            return self._index.get(self._commitment(commitment))
        except (TypeError, ValueError):
            return None

    def commitments(self):
        '''The issued commitments in the order of their leaves.'''
        return [self.leaf(index) for index in range(self.count)]

    def recent_roots(self):
        '''The current root first, then the earlier roots from the newest to the oldest (at most 8).'''
        return list(self._roots)

    def is_known_root(self, root):
        '''True for the current root and for the last 8 roots before it, as the contract accepts them.'''
        try:
            return field_element(root) in self._roots
        except (TypeError, ValueError):
            return False


class RevocationTree(MerkleTree):
    '''The tree of the revocation flags: leaf i is 1 once consent i is revoked, and 0 before.'''

    def __init__(self, revoked=None, depth=TREE_DEPTH):
        super().__init__(depth)
        for index in (revoked or []):
            self.revoke(index)

    def revoke(self, index):
        '''Set the flag of consent `index` (the on-chain step of Algorithm 6.4). There is no way
        back: no method clears a flag.'''
        if not self.is_revoked(index):
            self._set_leaf(index, 1)
        return self.root

    def is_revoked(self, index):
        return self.leaf(index) == 1

    def revoked(self):
        '''Leaf indices of the revoked consents, in ascending order.'''
        return sorted(self._levels[0])
