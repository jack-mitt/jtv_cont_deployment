from cryptography.fernet import Fernet

file = open("decryption", "rb")
key = file.read()
file.close()

with open("DevVars.txt", "rb") as f:
    data = f.read()

fernet = Fernet(key)
encrypted = fernet.encrypt(data)

with open("DevVars.txt.encrypted", "wb") as f:
    f.write(encrypted)
