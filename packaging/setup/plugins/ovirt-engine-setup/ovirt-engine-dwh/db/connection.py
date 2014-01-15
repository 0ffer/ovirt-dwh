#
# ovirt-engine-setup -- ovirt engine setup
# Copyright (C) 2013 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


"""Connection plugin."""


import socket
import gettext
_ = lambda m: gettext.dgettext(message=m, domain='ovirt-engine-dwh')


import psycopg2


from otopi import constants as otopicons
from otopi import transaction
from otopi import util
from otopi import plugin


from ovirt_engine_setup import constants as osetupcons
from ovirt_engine_setup import dwhconstants as odwhcons
from ovirt_engine_setup import database
from ovirt_engine_setup import dialog
from ovirt_engine_setup import util as osetuputil


@util.export
class Plugin(plugin.PluginBase):
    """Connection plugin."""

    class DBTransaction(transaction.TransactionElement):
        """yum transaction element."""

        def __init__(self, parent):
            self._parent = parent

        def __str__(self):
            return _("DWH database Transaction")

        def prepare(self):
            pass

        def abort(self):
            connection = self._parent.environment[odwhcons.DBEnv.CONNECTION]
            if connection is not None:
                connection.rollback()
                self._parent.environment[odwhcons.DBEnv.CONNECTION] = None

        def commit(self):
            connection = self._parent.environment[odwhcons.DBEnv.CONNECTION]
            if connection is not None:
                connection.commit()

    def _checkDbEncoding(self, environment):

        statement = database.Statement(
            environment=environment,
            dbenvkeys=odwhcons.Const.DWH_DB_ENV_KEYS,
        )
        encoding = statement.execute(
            statement="""
                show server_encoding
            """,
            ownConnection=True,
            transaction=False,
        )[0]['server_encoding']
        if encoding.lower() != 'utf8':
            raise RuntimeError(
                _(
                    'Encoding of the DWH database is {encoding}. '
                    'Engine installation is only supported on servers '
                    'with default encoding set to UTF8. Please fix the '
                    'default DB encoding before you continue'
                ).format(
                    encoding=encoding,
                )
            )

    def __init__(self, context):
        super(Plugin, self).__init__(context=context)

    @plugin.event(
        stage=plugin.Stages.STAGE_SETUP,
    )
    def _commands(self):
        self.environment[otopicons.CoreEnv.MAIN_TRANSACTION].append(
            self.DBTransaction(self)
        )

    @plugin.event(
        stage=plugin.Stages.STAGE_CUSTOMIZATION,
        name=odwhcons.Stages.DB_CONNECTION_CUSTOMIZATION,
        condition=lambda self: self.environment[odwhcons.CoreEnv.ENABLE],
        before=(
            osetupcons.Stages.DIALOG_TITLES_E_DATABASE,
        ),
        after=(
            osetupcons.Stages.DIALOG_TITLES_S_DATABASE,
        ),
    )
    def _customization(self):
        dbovirtutils = database.OvirtUtils(
            plugin=self,
            dbenvkeys=odwhcons.Const.DWH_DB_ENV_KEYS,
        )

        interactive = None in (
            self.environment[odwhcons.DBEnv.HOST],
            self.environment[odwhcons.DBEnv.PORT],
            self.environment[odwhcons.DBEnv.DATABASE],
            self.environment[odwhcons.DBEnv.USER],
            self.environment[odwhcons.DBEnv.PASSWORD],
        )

        if interactive:
            self.dialog.note(
                text=_(
                    "\n"
                    "ATTENTION\n"
                    "\n"
                    "Manual action required.\n"
                    "Please create database for ovirt-engine-dwh use. "
                    "Use the following commands as an example:\n"
                    "\n"
                    "create user engine_history password 'engine_history';\n"
                    "create database engine_history owner engine_history "
                    "template template0\n"
                    "encoding 'UTF8' lc_collate 'en_US.UTF-8'\n"
                    "lc_ctype 'en_US.UTF-8';\n"
                    "\n"
                    "Make sure that database can be accessed remotely.\n"
                    "\n"
                ),
            )

        connectionValid = False
        while not connectionValid:
            host = self.environment[odwhcons.DBEnv.HOST]
            port = self.environment[odwhcons.DBEnv.PORT]
            secured = self.environment[odwhcons.DBEnv.SECURED]
            securedHostValidation = self.environment[
                odwhcons.DBEnv.SECURED_HOST_VALIDATION
            ]
            db = self.environment[odwhcons.DBEnv.DATABASE]
            user = self.environment[odwhcons.DBEnv.USER]
            password = self.environment[odwhcons.DBEnv.PASSWORD]

            if host is None:
                while True:
                    host = self.dialog.queryString(
                        name='OVESETUP_DWH_DB_HOST',
                        note=_('DWH database host [@DEFAULT@]: '),
                        prompt=True,
                        default=odwhcons.Defaults.DEFAULT_DB_HOST,
                    )
                    try:
                        socket.getaddrinfo(host, None)
                        break  # do while missing in python
                    except socket.error as e:
                        self.logger.error(
                            _('Host is invalid: {error}').format(
                                error=e.strerror
                            )
                        )

            if port is None:
                while True:
                    try:
                        port = osetuputil.parsePort(
                            self.dialog.queryString(
                                name='OVESETUP_DWH_DB_PORT',
                                note=_('DWH database port [@DEFAULT@]: '),
                                prompt=True,
                                default=odwhcons.Defaults.DEFAULT_DB_PORT,
                            )
                        )
                        break  # do while missing in python
                    except ValueError:
                        pass

            if secured is None:
                secured = dialog.queryBoolean(
                    dialog=self.dialog,
                    name='OVESETUP_DWH_DB_SECURED',
                    note=_(
                        'DWH database secured connection (@VALUES@) '
                        '[@DEFAULT@]: '
                    ),
                    prompt=True,
                    default=odwhcons.Defaults.DEFAULT_DB_SECURED,
                )

            if not secured:
                securedHostValidation = False

            if securedHostValidation is None:
                securedHostValidation = dialog.queryBoolean(
                    dialog=self.dialog,
                    name='OVESETUP_DWH_DB_SECURED_HOST_VALIDATION',
                    note=_(
                        'DWH database host name validation in secured '
                        'connection (@VALUES@) [@DEFAULT@]: '
                    ),
                    prompt=True,
                    default=True,
                ) == 'yes'

            if db is None:
                db = self.dialog.queryString(
                    name='OVESETUP_DWH_DB_DATABASE',
                    note=_('DWH database name [@DEFAULT@]: '),
                    prompt=True,
                    default=odwhcons.Defaults.DEFAULT_DB_DATABASE,
                )

            if user is None:
                user = self.dialog.queryString(
                    name='OVESETUP_DWH_DB_USER',
                    note=_('DWH database user [@DEFAULT@]: '),
                    prompt=True,
                    default=odwhcons.Defaults.DEFAULT_DB_USER,
                )

            if password is None:
                password = self.dialog.queryString(
                    name='OVESETUP_DWH_DB_PASSWORD',
                    note=_('DWH database password: '),
                    prompt=True,
                    hidden=True,
                )

                self.environment[otopicons.CoreEnv.LOG_FILTER].append(password)

            dbenv = {
                odwhcons.DBEnv.HOST: host,
                odwhcons.DBEnv.PORT: port,
                odwhcons.DBEnv.SECURED: secured,
                odwhcons.DBEnv.SECURED_HOST_VALIDATION: (
                    securedHostValidation
                ),
                odwhcons.DBEnv.USER: user,
                odwhcons.DBEnv.PASSWORD: password,
                odwhcons.DBEnv.DATABASE: db,
            }

            if interactive:
                try:
                    dbovirtutils.tryDatabaseConnect(dbenv)
                    self._checkDbEncoding(dbenv)
                    self.environment.update(dbenv)
                    connectionValid = True
                except RuntimeError as e:
                    self.logger.error(
                        _('Cannot connect to DWH database: {error}').format(
                            error=e,
                        )
                    )
            else:
                # this is usally reached in provisioning
                # or if full ansewr file
                self.environment.update(dbenv)
                connectionValid = True

        try:
            self.environment[
                odwhcons.DBEnv.NEW_DATABASE
            ] = dbovirtutils.isNewDatabase()
        except:
            self.logger.debug('database connection failed', exc_info=True)

    @plugin.event(
        stage=plugin.Stages.STAGE_MISC,
        name=odwhcons.Stages.DB_CONNECTION_AVAILABLE,
        condition=lambda self: self.environment[odwhcons.CoreEnv.ENABLE],
        after=(
            odwhcons.Stages.DB_SCHEMA,
        ),
    )
    def _connection(self):
        # must be here as we do not have database at validation
        self.environment[
            odwhcons.DBEnv.CONNECTION
        ] = psycopg2.connect(
            host=self.environment[odwhcons.DBEnv.HOST],
            port=self.environment[odwhcons.DBEnv.PORT],
            user=self.environment[odwhcons.DBEnv.USER],
            password=self.environment[odwhcons.DBEnv.PASSWORD],
            database=self.environment[odwhcons.DBEnv.DATABASE],
        )
        self.environment[
            odwhcons.DBEnv.STATEMENT
        ] = database.Statement(
            environment=self.environment,
            dbenvkeys=odwhcons.Const.DWH_DB_ENV_KEYS,
        )


# vim: expandtab tabstop=4 shiftwidth=4
