import datetime
import logging
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from imap_tools import AND, MailBox

logger = logging.getLogger(__name__)

def email_connection(resource, **kwargs):
    """
    Connect to an e-mail server, search for the most recent e-mail matching
    the given criteria and save its attachments to the resource path.
    """

    # Get resource defained criteria for e-mail search
    dptel_extract = resource.custom.get('dpetl_extract', {})
    dptel_extract.setdefault('criteria', {})

    # Get e-mail connection details from env vars and custom properties
    load_dotenv(find_dotenv(usecwd=True))
    email_user = os.environ.get('EMAIL_USER')
    email_pwd = os.environ.get('EMAIL_PWD')
    email_imap = os.environ.get('EMAIL_IMAP')
    email_box = dptel_extract.get('mailbox', 'INBOX')

    if not all([email_user, email_pwd, email_imap]):
        logger.error(
            ('Missing one of the required e-mail environment variables:'
            'email_user, email_pwd or email_imap.')
        )
        return

    with MailBox(email_imap).login(email_user, email_pwd) as mailbox:
        logger.info('Connected to e-mail successfully.')

        mailbox.folder.set(email_box)
        logger.info(
            'E-mail folder selected.', extra={'folder': email_box}
        )

        extract_email(mailbox, resource, **kwargs)

        if len(resource.extrapaths) > 0:
            for extrapath in resource.extrapaths:
                resource.path = extrapath
                extract_email(mailbox, resource, **kwargs)


def extract_email(mailbox, resource, **kwargs):
    """
    Extract the most recent e-mail matching a subject and save its attachments
    to the given resource path.
    """
    try:
        package_name = resource.package.name
        resource_path = Path(resource.path)
        name = resource_path.stem
        criteria = resource.custom.get('dpetl_extract', {}).get('criteria', {})
        criteria['subject'] = f'{package_name}_{name}'
        criteria['date_gte'] = datetime.date.today()  if kwargs.get('--today-email') else None
        resource_path.parent.mkdir(parents=True, exist_ok=True)
        search_query = AND(**criteria)
        logger.debug(
            'Searching for e-mails.', extra={'criteria': str(criteria)}
        )

        msgs = list(mailbox.fetch(search_query, limit=1, reverse=True))

        if not msgs:
            logger.warning(
                'No e-mail found matching the criteria.',
                extra={'criteria': str(criteria)},
            )
            return
        elif len(msgs) > 1:
            # No neet to stop the code, just inform
            logger.warning(
                'More than one e-mail was found matching the criteria.',
                extra={'criteria': str(criteria)},
            )

        msg = msgs[0]

        logger.info(
            'E-mail found.',
            extra={
                'subject': msg.subject,
                'date': str(msg.date),
                'from': msg.from_,
            },
        )

        if not msg.attachments:
            logger.warning(
                'E-mail found but no attachments presented.',
                extra={'subject': msg.subject},
            )
            return
        elif len(msg.attachments) > 1:
            # No neet to stop the code, just inform
            logger.warning(
                'More than one attachment file found.',
                extra={'criteria': str(criteria)},
            )

        for index, att in enumerate(msg.attachments):
            logger.debug(
                'Processing attachment.',
                extra={
                    'filename': att.filename,
                    'size_bytes': len(att.payload),
                },
            )

            path = (
                resource_path
                if index == 0
                else resource_path.with_name(
                    f'{resource_path.name}_{index}'
                )
            )
            # Do not need to write in chuncks because mail fails are small
            with open(path, 'wb') as f:
                f.write(att.payload)

            logger.info(
                'Attachment saved successfully.',
                extra={
                    'filename': att.filename,
                    'saved_to': str(path),
                },
            )

        logger.info('E-mail extraction completed successfully.')

    except Exception:
        logger.exception('Unexpected error during e-mail extraction.')
