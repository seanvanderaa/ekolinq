import json

def submitContact(name, email, message):
    id = 0
    if name:
        id +=1
    if email:
        id +=1
    if message:
        id +=1

    print("Name:", name, "Email: ", email, "Message: ", message)
    if id==3:
        return {
            "valid": True,
            "reason": ""
        }
    else:
        return {
            "valid": False,
            "reason": "Something broke!"
        }