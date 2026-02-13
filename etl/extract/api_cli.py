import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import date
from imap_tools import MailBox, AND
from frictionless import Package
from etl.helpers import resources_iteration


def api(subparsers):
    new_cmd = subparsers.add_parser('api',
        aliases=['a'],
        help='Extract resources from API call.'
    )
    new_cmd.set_defaults(func=handle_command)

def handle_command(args):

    resources_iteration(function=extract_email)


# TODO: pasta destino = data_raw como padrão, mas poderá ser modificada.
# Loop para recursos listados no datapackage.json
# Não preciso desta função git_push_geral()

def extract_email(resource):

    # TODO: Pass variable to not create folder and exit if it not exists
    # would it be useful?
    resource_path = Path(resource.path)
    resource_path.parent.mkdir(parents=True, exist_ok=True)

    # TODO: Pass variable to set different subject if needed
    # Set up email subject to search
    today = date.today()
    formatted_today = today.strftime('%Y-%m-%d')
    subject = f'{resource.name}-{formatted_today}'

    load_dotenv()
    user = os.getenv('EMAIL_USER')
    password = os.getenv('EMAIL_PWD')
    # breakpoint()

    try:
        # TODO: Passar parâmetro para aceitar qualquer e-mail (não só Gmail)
        # Buscar email e senha usando dotenv
        with MailBox('imap.gmail.com').login(user, password) as mailbox:

            # Switch to Trash folder
            mailbox.folder.set('[Gmail]/Trash')

            # CRITÉRIO: Assunto específico E Data de hoje
            # Não vi ele filtrando a pasta de dentro do e-mail, tipo IMBOX ou Trash
            criterios = AND(subject=subject, date=today)

            # Pega apenas 1 email (o mais recente de hoje, se houver duplicidade)
            msgs = list(mailbox.fetch(criterios, limit=1, reverse=True))

            if not msgs:
                print(f"❌ Erro: consulta não encontrada para asusnto:'{subject}'.")

            for msg in msgs:
                print(f"📧 E-mail localizado: '{msg.subject}'")

                for att in msg.attachments:

                    with open(resource_path, 'wb') as f:
                        f.write(att.payload)

                    print(f"   ✅ Arquivo salvo em: {resource.path}")


    except Exception as e:
        print(f"❌ Erro crítico de conexão: {e}")
        return
