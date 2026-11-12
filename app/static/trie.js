// Prefix search over problem names, ported from AlgoReady.
//
// Changes from AlgoReady's version:
//  - every word of a name is inserted, so "tree" finds "Game on Growing Tree"
//  - each node keeps at most CAP names, so memory stays bounded
//    (AlgoReady kept every matching name at every node)
// Lookup cost is O(k) for a prefix of length k, plus copying at most CAP results.

const CAP = 50;

class TrieNode {
  constructor() {
    this.children = new Map();
    this.names = [];
  }
}

class Trie {
  constructor() {
    this.root = new TrieNode();
  }

  insertKey(key, name) {
    let node = this.root;
    for (const ch of key) {
      if (!node.children.has(ch)) node.children.set(ch, new TrieNode());
      node = node.children.get(ch);
      if (node.names.length < CAP && node.names[node.names.length - 1] !== name) node.names.push(name);
    }
  }

  insert(name) {
    const lower = name.toLowerCase();
    // the full name, then the name starting at each later word
    this.insertKey(lower, name);
    for (let i = 1; i < lower.length; i++) {
      if (lower[i - 1] === " ") this.insertKey(lower.slice(i), name);
    }
  }

  searchPrefix(prefix, limit = CAP) {
    let node = this.root;
    for (const ch of prefix.toLowerCase()) {
      node = node.children.get(ch);
      if (!node) return [];
    }
    return [...new Set(node.names)].slice(0, limit);
  }
}

if (typeof module !== "undefined") module.exports = { Trie };
