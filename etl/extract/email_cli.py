import os
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from datetime import date
from imap_tools import MailBox, AND
from frictionless import Package

def extract_email(resource, **kwargs):

    resource_path = Path(resource.path)
    resource_path.parent.mkdir(parents=True, exist_ok=True)
    subject = resource.custom.get('subject', resource.name)

    load_dotenv(find_dotenv(usecwd=True))
    email_user = os.environ.get('EMAIL_USER')
    email_pwd = os.environ.get('EMAIL_PWD')
    email_smtp = os.environ.get('EMAIL_SMTP')
    email_box =  os.environ.get('EMAIL_BOX')
    breakpoint()

    try:
        # TODO: Passar parâmetro para aceitar qualquer e-mail (não só Gmail)
        # Buscar email e senha usando dotenv
        with MailBox(email_smtp).login(email_user, email_pwd) as mailbox:

            mailbox.folder.set(email_box)

            # CRITÉRIO: Assunto específico
            # TODO: Receive arguments as **kwargs to allow more flexible criteria, e.g., date, sender, etc.
            criterios = AND(subject=subject)

            # get only 1 email (the most recent one with the subject, if there are duplicates)
            msgs = list(mailbox.fetch(criterios, limit=1, reverse=True))

            if not msgs:
                # TODO: Receive arguments as **kwargs to allow more flexible criteria in this message
                print(f"❌ Error: nothing found for the subject:'{subject}'.")

            for msg in msgs:
                print(f"📧 E-mail found: '{msg.subject}'")

                for att in msg.attachments:

                    with open(resource_path, 'wb') as f:
                        f.write(att.payload)

                    print(f"   ✅ File saved in: {resource.path}")


    except Exception as e:
        print(f"❌ Error in the connection: {e}")
        return
