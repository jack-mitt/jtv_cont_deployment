from cryptography.fernet import Fernet

file = open("decryption", "rb")
key = file.read()
file.close()

with open("DevVars.txt.encrypted", "rb") as f:
    data = f.read()

fernet = Fernet(key)
encrypted = fernet.decrypt(data)

with open("DevVars.txt.decrypted", "wb") as f:
    f.write(encrypted)
