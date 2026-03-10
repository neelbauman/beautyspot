import doorstop
tree = doorstop.build()
doc = tree.documents[0]
item = list(doc)[0]
print("UID:", item.uid)
print("Doc Prefix:", item.document.prefix)
