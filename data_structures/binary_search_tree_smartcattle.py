"""Academic example of a binary search tree over the SmartCattle herd registry.

The herd is registered by ear tag number (the "chapeta"). The questions asked of
that registry are: is tag 47 ours, list the herd in tag order, and which animals
carry tags 100 to 199 (one paddock's batch). A binary search tree answers all
three from the same structure:

1. **Search halves the candidates at each step.** Every node keeps smaller tags
   on its left and larger ones on its right, so finding a tag follows one path
   from the root: O(log n) while the tree stays balanced, against O(n) for a
   list that has to be read until the tag turns up.

2. **The in-order walk is already sorted.** Left subtree, node, right subtree
   visits the tags in ascending order, with no sort step.

3. **A range query skips whole branches.** If a node's tag is below the range,
   nothing on its left can be in it, so that subtree is never visited.

The cost, stated plainly: the tree is only as good as its shape. Tags inserted
in ascending order (1, 2, 3, ...) build a chain where every node has only a
right child, and every operation degrades to O(n). A self-balancing tree (AVL,
red-black) fixes that; this example keeps the plain version so the rules stay
visible, and `height()` shows the effect.

Not used by the API. Individual animal identities such as ear tags assume a
future phase; the records here are simplified teaching examples.
"""

from collections import deque
from dataclasses import dataclass


@dataclass
class Animal:
    tag: int
    name: str
    breed: str
    weight_kg: float


class Node:
    """One animal, with the smaller tags to its left and the larger to its right."""

    def __init__(self, animal: Animal) -> None:
        self.animal: Animal = animal
        self.left: Node | None = None
        self.right: Node | None = None


class HerdRegistry:
    """The herd ordered by ear tag. A tag appears at most once."""

    def __init__(self) -> None:
        self.root: Node | None = None
        self._size = 0

    def insert(self, animal: Animal) -> bool:
        """Adds an animal. False if the tag is already registered: two animals cannot share a tag."""
        if self.root is None:
            self.root = Node(animal)
            self._size = 1
            return True
        current = self.root
        while True:
            if animal.tag == current.animal.tag:
                return False
            side = "left" if animal.tag < current.animal.tag else "right"
            child = getattr(current, side)
            if child is None:
                setattr(current, side, Node(animal))
                self._size += 1
                return True
            current = child

    def search(self, tag: int) -> Animal | None:
        """Follows one path from the root, discarding half of what is left at each step."""
        current = self.root
        while current is not None:
            if tag == current.animal.tag:
                return current.animal
            current = current.left if tag < current.animal.tag else current.right
        return None

    def remove(self, tag: int) -> bool:
        """Removes an animal sold or lost. False if the tag is not registered.

        The three cases of deletion:
        - a leaf just goes;
        - a node with one child is replaced by that child;
        - a node with two children takes the animal of its in-order successor
          (the smallest tag on its right), and that successor, which has no
          left child, is removed from the right subtree instead.
        """
        self.root, removed = self._remove(self.root, tag)
        if removed:
            self._size -= 1
        return removed

    def _remove(self, node: Node | None, tag: int) -> tuple[Node | None, bool]:
        if node is None:
            return None, False
        if tag < node.animal.tag:
            node.left, removed = self._remove(node.left, tag)
            return node, removed
        if tag > node.animal.tag:
            node.right, removed = self._remove(node.right, tag)
            return node, removed
        if node.left is None:
            return node.right, True
        if node.right is None:
            return node.left, True
        successor = node.right
        while successor.left is not None:
            successor = successor.left
        node.animal = successor.animal
        node.right, _ = self._remove(node.right, successor.animal.tag)
        return node, True

    def in_order(self) -> list[Animal]:
        """Ascending tag order: the herd list, sorted for free."""
        animals: list[Animal] = []

        def walk(node: Node | None) -> None:
            if node is not None:
                walk(node.left)
                animals.append(node.animal)
                walk(node.right)

        walk(self.root)
        return animals

    def pre_order(self) -> list[Animal]:
        """Node before its subtrees. Re-inserting in this order rebuilds the same tree, so it suits a backup."""
        animals: list[Animal] = []

        def walk(node: Node | None) -> None:
            if node is not None:
                animals.append(node.animal)
                walk(node.left)
                walk(node.right)

        walk(self.root)
        return animals

    def post_order(self) -> list[Animal]:
        """Subtrees before their node: children are handled before the node that holds them."""
        animals: list[Animal] = []

        def walk(node: Node | None) -> None:
            if node is not None:
                walk(node.left)
                walk(node.right)
                animals.append(node.animal)

        walk(self.root)
        return animals

    def by_level(self) -> list[list[int]]:
        """The tags level by level from the root (breadth first, with a queue). Shows the tree's shape."""
        if self.root is None:
            return []
        levels: list[list[int]] = []
        pending: deque[Node] = deque([self.root])
        while pending:
            level: list[int] = []
            for _ in range(len(pending)):
                node = pending.popleft()
                level.append(node.animal.tag)
                pending.extend(child for child in (node.left, node.right) if child is not None)
            levels.append(level)
        return levels

    def in_range(self, low: int, high: int) -> list[Animal]:
        """Animals whose tag is between low and high, inclusive, in tag order.

        Prunes: below the range nothing on the left can match, above it nothing on the right.
        """
        animals: list[Animal] = []

        def walk(node: Node | None) -> None:
            if node is None:
                return
            if low < node.animal.tag:
                walk(node.left)
            if low <= node.animal.tag <= high:
                animals.append(node.animal)
            if node.animal.tag < high:
                walk(node.right)

        walk(self.root)
        return animals

    def lowest(self) -> Animal | None:
        """The smallest tag: always the leftmost node."""
        current = self.root
        if current is None:
            return None
        while current.left is not None:
            current = current.left
        return current.animal

    def highest(self) -> Animal | None:
        """The largest tag: always the rightmost node."""
        current = self.root
        if current is None:
            return None
        while current.right is not None:
            current = current.right
        return current.animal

    def height(self) -> int:
        """Levels from the root to the deepest leaf; 0 when empty. log2(n) is the best case, n the worst."""

        def depth(node: Node | None) -> int:
            return 0 if node is None else 1 + max(depth(node.left), depth(node.right))

        return depth(self.root)

    def __len__(self) -> int:
        return self._size

    def __contains__(self, tag: object) -> bool:
        return isinstance(tag, int) and self.search(tag) is not None


if __name__ == "__main__":
    registry = HerdRegistry()
    for tag, name, breed, weight in [
        (50, "Lucero", "Brahman", 420.0), (30, "Canela", "Holstein", 510.5), (70, "Mariposa", "Normando", 465.0),
        (20, "Pinta", "Gyr", 380.0), (40, "Estrella", "Brahman", 455.0), (60, "Morena", "Holstein", 530.0),
        (80, "Paloma", "Cebú", 400.0),
    ]:
        registry.insert(Animal(tag, name, breed, weight))

    print(f"Animals registered: {len(registry)}  height: {registry.height()}")
    print("Levels:", registry.by_level())
    print("In order:", [animal.tag for animal in registry.in_order()])
    print("Pre order:", [animal.tag for animal in registry.pre_order()])
    print("Post order:", [animal.tag for animal in registry.post_order()])
    print("Search 60:", registry.search(60))
    print("Tags 35 to 65:", [animal.name for animal in registry.in_range(35, 65)])
    print("Duplicate tag 40 accepted?", registry.insert(Animal(40, "Otra", "Gyr", 300.0)))

    registry.remove(50)  # The root, with two children: its successor (60) takes its place.
    print("After selling tag 50, levels:", registry.by_level())

    chain = HerdRegistry()
    for tag in range(1, 8):
        chain.insert(Animal(tag, f"Cow-{tag}", "Brahman", 400.0))
    print(f"Inserted in ascending order: height {chain.height()} for {len(chain)} animals (a chain, not a tree)")
