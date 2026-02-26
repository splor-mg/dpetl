import logging
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from imap_tools import AND, MailBox

logger = logging.getLogger(__name__)


def extract_email(resource, **kwargs):
    """
    Extract the most recent email matching a subject and save its attachments
    to the given resource path.
    """

    try:
        resource_path = Path(resource.path)
        dptel_extract = resource.custom.get('dptel_extract', {})
        criteria = dptel_extract.get('criteria', {})
        # Only set subject to resource.name if this key doesn't exists
        # on dpetl_extract.criteria custom property
        # Could be dangerous because it changes criteria dict in place
        criteria.setdefault('subject', resource.name)

        resource_path.parent.mkdir(parents=True, exist_ok=True)
        load_dotenv(find_dotenv(usecwd=True))
        email_user = os.environ.get('EMAIL_USER')
        email_pwd = os.environ.get('EMAIL_PWD')
        email_smtp = os.environ.get('EMAIL_SMTP')
        email_box = dptel_extract.get('mailbox', 'INBOX')

        if not all([email_user, email_pwd, email_smtp]):
            logger.error(
                'Missing one of the required email environment variables: \
                email_user, email_pwd or email_smtp.'
            )
            return

        if 'mailbox' not in dptel_extract:
            logger.debug("Using default mailbox 'INBOX'.")

        logger.debug(
            'Connecting to mailbox.',
            extra={
                'smtp_server': email_smtp,
                'mailbox': email_box,
                'user': email_user,
            },
        )

        with MailBox(email_smtp).login(email_user, email_pwd) as mailbox:
            logger.info('Connected to mailbox successfully.')

            mailbox.folder.set(email_box)
            logger.info(
                'Mailbox folder selected.', extra={'folder': email_box}
            )

            search_query = AND(**criteria)
            logger.debug(
                'Searching emails.', extra={'criteria': str(criteria)}
            )

            msgs = list(mailbox.fetch(search_query, limit=1, reverse=True))

            if not msgs:
                logger.warning(
                    'No email found matching the criteria.',
                    extra={'criteria': str(criteria)},
                )
                return
            elif len(msgs) > 1:
                # No neet to stop the code, just inform
                logger.warning(
                    'More than one email was found matching the criteria.',
                    extra={'criteria': str(criteria)},
                )

            msg = msgs[0]

            logger.info(
                'Email found.',
                extra={
                    'subject': msg.subject,
                    'date': str(msg.date),
                    'from': msg.from_,
                },
            )

            if not msg.attachments:
                logger.warning(
                    'Email found but no attachments presented.',
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

        logger.info('Email extraction completed successfully.')

    except Exception:
        logger.exception('Unexpected error during email extraction.')
