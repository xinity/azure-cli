# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint:disable=too-many-lines

import itertools
from enum import Enum

from azure.mgmt.sql.models import (
    Database,
    ElasticPool,
    ElasticPoolPerDatabaseSettings,
    ImportExtensionRequest,
    ExportRequest,
    ManagedDatabase,
    ManagedInstance,
    ManagedInstanceAdministrator,
    Server,
    ServerAzureADAdministrator,
    Sku,
    AuthenticationType,
    BlobAuditingPolicyState,
    CatalogCollationType,
    CreateMode,
    DatabaseLicenseType,
    ElasticPoolLicenseType,
    SampleName,
    SecurityAlertPolicyState,
    SecurityAlertPolicyEmailAccountAdmins,
    ServerConnectionType,
    ServerKeyType,
    StorageKeyType,
    TransparentDataEncryptionStatus
)

from azure.cli.core.commands.parameters import (
    get_three_state_flag,
    get_enum_type,
    get_resource_name_completion_list,
    get_location_type,
    tags_type,
    resource_group_name_type
)

from azure.cli.core.commands.validators import (
    get_default_location_from_resource_group
)

from knack.arguments import CLIArgumentType, ignore_type

from .custom import (
    ClientAuthenticationType,
    ClientType,
    ComputeModelType,
    DatabaseCapabilitiesAdditionalDetails,
    ElasticPoolCapabilitiesAdditionalDetails,
    FailoverPolicyType
)

from ._validators import (
    create_args_for_complex_type,
    validate_managed_instance_storage_size,
    validate_subnet
)


#####
#        SizeWithUnitConverter - consider moving to common code (azure.cli.core.commands.parameters)
#####


class SizeWithUnitConverter():  # pylint: disable=too-few-public-methods

    def __init__(
            self,
            unit='kB',
            result_type=int,
            unit_map=None):
        self.unit = unit
        self.result_type = result_type
        self.unit_map = unit_map or dict(B=1, kB=1024, MB=1024 * 1024, GB=1024 * 1024 * 1024,
                                         TB=1024 * 1024 * 1024 * 1024)

    def __call__(self, value):
        numeric_part = ''.join(itertools.takewhile(str.isdigit, value))
        unit_part = value[len(numeric_part):]

        try:
            uvals = (self.unit_map[unit_part] if unit_part else 1) / \
                (self.unit_map[self.unit] if self.unit else 1)
            return self.result_type(uvals * self.result_type(numeric_part))
        except KeyError:
            raise ValueError()

    def __repr__(self):
        return 'Size (in {}) - valid units are {}.'.format(
            self.unit,
            ', '.join(sorted(self.unit_map, key=self.unit_map.__getitem__)))


#####
#        Reusable param type definitions
#####


sku_arg_group = 'Performance Level'

sku_component_arg_group = 'Performance Level (components)'

serverless_arg_group = 'Serverless offering'

server_configure_help = 'You can configure the default using `az configure --defaults sql-server=<name>`'


def get_location_type_with_default_from_resource_group(cli_ctx):
    return CLIArgumentType(
        arg_type=get_location_type(cli_ctx),
        required=False,
        validator=get_default_location_from_resource_group)


server_param_type = CLIArgumentType(
    options_list=['--server', '-s'],
    configured_default='sql-server',
    help='Name of the Azure SQL server. ' + server_configure_help,
    completer=get_resource_name_completion_list('Microsoft.SQL/servers'),
    # Allow --ids command line argument. id_part=name is 1st name in uri
    id_part='name')

available_param_type = CLIArgumentType(
    options_list=['--available', '-a'],
    help='If specified, show only results that are available in the specified region.')

tier_param_type = CLIArgumentType(
    arg_group=sku_component_arg_group,
    options_list=['--tier', '--edition', '-e'])

capacity_param_type = CLIArgumentType(
    arg_group=sku_component_arg_group,
    options_list=['--capacity', '-c'])

capacity_or_dtu_param_type = CLIArgumentType(
    arg_group=sku_component_arg_group,
    options_list=['--capacity', '-c', '--dtu'])

family_param_type = CLIArgumentType(
    arg_group=sku_component_arg_group,
    options_list=['--family', '-f'])

elastic_pool_id_param_type = CLIArgumentType(
    arg_group=sku_arg_group,
    options_list=['--elastic-pool'])

compute_model_param_type = CLIArgumentType(
    arg_group=serverless_arg_group,
    options_list=['--compute-model'],
    help='The compute model of the database.',
    arg_type=get_enum_type(ComputeModelType))

auto_pause_delay_param_type = CLIArgumentType(
    arg_group=serverless_arg_group,
    options_list=['--auto-pause-delay'],
    help='Time in minutes after which database is automatically paused. '
    'A value of -1 means that automatic pause is disabled.')

min_capacity_param_type = CLIArgumentType(
    arg_group=serverless_arg_group,
    options_list=['--min-capacity'],
    help='Minimal capacity that database will always have allocated, if not paused')

max_size_bytes_param_type = CLIArgumentType(
    options_list=['--max-size'],
    type=SizeWithUnitConverter('B', result_type=int),
    help='The max storage size. If no unit is specified, defaults to bytes (B).')

zone_redundant_param_type = CLIArgumentType(
    options_list=['--zone-redundant', '-z'],
    help='Specifies whether to enable zone redundancy',
    arg_type=get_three_state_flag())

managed_instance_param_type = CLIArgumentType(
    options_list=['--managed-instance', '--mi'],
    help='Name of the Azure SQL managed instance.')

kid_param_type = CLIArgumentType(
    options_list=['--kid', '-k'],
    help='The Azure Key Vault key identifier of the server key. An example key identifier is '
    '"https://YourVaultName.vault.azure.net/keys/YourKeyName/01234567890123456789012345678901"')

server_key_type_param_type = CLIArgumentType(
    options_list=['--server-key-type', '-t'],
    help='The type of the server key',
    arg_type=get_enum_type(ServerKeyType))

storage_param_type = CLIArgumentType(
    options_list=['--storage'],
    type=SizeWithUnitConverter('GB', result_type=int, unit_map=dict(B=1.0 / (1024 * 1024 * 1024),
                                                                    kB=1.0 / (1024 * 1024),
                                                                    MB=1.0 / 1024,
                                                                    GB=1,
                                                                    TB=1024)),
    help='The storage size. If no unit is specified, defaults to gigabytes (GB).',
    validator=validate_managed_instance_storage_size)

grace_period_param_type = CLIArgumentType(
    help='Interval in hours before automatic failover is initiated '
    'if an outage occurs on the primary server. '
    'This indicates that Azure SQL Database will not initiate '
    'automatic failover before the grace period expires. '
    'Please note that failover operation with --allow-data-loss option '
    'might cause data loss due to the nature of asynchronous synchronization.')

allow_data_loss_param_type = CLIArgumentType(
    help='Complete the failover even if doing so may result in data loss. '
    'This will allow the failover to proceed even if a primary database is unavailable.')

aad_admin_login_param_type = CLIArgumentType(
    options_list=['--display-name', '-u'],
    help='Display name of the Azure AD administrator user or group.')

aad_admin_sid_param_type = CLIArgumentType(
    options_list=['--object-id', '-i'],
    help='The unique ID of the Azure AD administrator.')

db_service_objective_examples = 'Basic, S0, P1, GP_Gen4_1, BC_Gen5_2, GP_Gen5_S_8.'
dw_service_objective_examples = 'DW100, DW1000c'


###############################################
#                sql db                       #
###############################################


class Engine(Enum):  # pylint: disable=too-few-public-methods
    """SQL RDBMS engine type."""
    db = 'db'
    dw = 'dw'


def _configure_db_create_params(
        arg_ctx,
        engine,
        create_mode):
    """
    Configures params for db/dw create/update commands.

    The PUT database REST API has many parameters and many modes (`create_mode`) that control
    which parameters are valid. To make it easier for CLI users to get the param combinations
    correct, these create modes are separated into different commands (e.g.: create, copy,
    restore, etc).

    On top of that, some create modes and some params are not allowed if the database edition is
    DataWarehouse. For this reason, regular database commands are separated from datawarehouse
    commands (`db` vs `dw`.)

    As a result, the param combination matrix is a little complicated. This function configures
    which params are ignored for a PUT database command based on a command's SQL engine type and
    create mode.

    engine: Engine enum value (e.g. `db`, `dw`)
    create_mode: Valid CreateMode enum value (e.g. `default`, `copy`, etc)
    """

    # DW does not support all create modes. Check that engine and create_mode are consistent.
    if engine == Engine.dw and create_mode not in [
            CreateMode.default,
            CreateMode.point_in_time_restore,
            CreateMode.restore]:
        raise ValueError('Engine {} does not support create mode {}'.format(engine, create_mode))

    # Create args that will be used to build up the Database object
    create_args_for_complex_type(
        arg_ctx, 'parameters', Database, [
            'catalog_collation',
            'collation',
            'elastic_pool_id',
            'license_type',
            'max_size_bytes',
            'name',
            'restore_point_in_time',
            'sample_name',
            'sku',
            'source_database_deletion_date',
            'tags',
            'zone_redundant',
            'auto_pause_delay',
            'min_capacity',
            'compute_model'
        ])

    # Create args that will be used to build up the Database's Sku object
    create_args_for_complex_type(
        arg_ctx, 'sku', Sku, [
            'capacity',
            'family',
            'name',
            'tier',
        ])

    arg_ctx.argument('name',  # Note: this is sku name, not database name
                     options_list=['--service-objective'],
                     arg_group=sku_arg_group,
                     required=False,
                     help='The service objective for the new database. For example: ' +
                     (db_service_objective_examples if engine == Engine.db else dw_service_objective_examples))

    arg_ctx.argument('elastic_pool_id',
                     arg_type=elastic_pool_id_param_type,
                     help='The name or resource id of the elastic pool to create the database in.')

    arg_ctx.argument('compute_model',
                     arg_type=compute_model_param_type)

    arg_ctx.argument('auto_pause_delay',
                     arg_type=auto_pause_delay_param_type)

    arg_ctx.argument('min_capacity',
                     arg_type=min_capacity_param_type)

    # Only applicable to default create mode. Also only applicable to db.
    if create_mode != CreateMode.default or engine != Engine.db:
        arg_ctx.ignore('sample_name')
        arg_ctx.ignore('catalog_collation')
        arg_ctx.ignore('read_scale')

    # Only applicable to point in time restore or deleted restore create mode.
    if create_mode not in [CreateMode.restore, CreateMode.point_in_time_restore]:
        arg_ctx.ignore('restore_point_in_time', 'source_database_deletion_date')

    # 'collation', 'tier', and 'max_size_bytes' are ignored (or rejected) when creating a copy
    # or secondary because their values are determined by the source db.
    if create_mode in [CreateMode.copy, CreateMode.secondary]:
        arg_ctx.ignore('collation', 'tier', 'max_size_bytes')

    # collation and max_size_bytes are ignored when restoring because their values are determined by
    # the source db.
    if create_mode in [CreateMode.restore, CreateMode.point_in_time_restore]:
        arg_ctx.ignore('collation', 'max_size_bytes')

    if engine == Engine.dw:
        # Elastic pool is only for SQL DB.
        arg_ctx.ignore('elastic_pool_id')

        # Edition is always 'DataWarehouse'
        arg_ctx.ignore('tier')

        # License types do not yet exist for DataWarehouse
        arg_ctx.ignore('license_type')

        # Family is not applicable to DataWarehouse
        arg_ctx.ignore('family')

        # Provisioning with capacity is not applicable to DataWarehouse
        arg_ctx.ignore('capacity')

        # Serverless offerings are not applicable to DataWarehouse
        arg_ctx.ignore('auto_pause_delay')
        arg_ctx.ignore('min_capacity')
        arg_ctx.ignore('compute_model')


# pylint: disable=too-many-statements
def load_arguments(self, _):

    with self.argument_context('sql') as c:
        c.argument('location_name', arg_type=get_location_type(self.cli_ctx))
        c.argument('usage_name', options_list=['--usage', '-u'])
        c.argument('tags', arg_type=tags_type)
        c.argument('allow_data_loss',
                   help='If specified, the failover operation will allow data loss.')

    with self.argument_context('sql db') as c:
        c.argument('server_name',
                   arg_type=server_param_type)

        c.argument('database_name',
                   options_list=['--name', '-n'],
                   help='Name of the Azure SQL Database.',
                   # Allow --ids command line argument. id_part=child_name_1 is 2nd name in uri
                   id_part='child_name_1')

        c.argument('max_size_bytes',
                   arg_type=max_size_bytes_param_type)

        creation_arg_group = 'Creation'

        c.argument('collation',
                   arg_group=creation_arg_group)

        c.argument('catalog_collation',
                   arg_group=creation_arg_group,
                   arg_type=get_enum_type(CatalogCollationType))

        c.argument('sample_name',
                   arg_group=creation_arg_group,
                   arg_type=get_enum_type(SampleName))

        c.argument('license_type',
                   arg_type=get_enum_type(DatabaseLicenseType))

        # Needs testing
        c.ignore('read_scale')
        # c.argument('read_scale',
        #            arg_type=get_three_state_flag(DatabaseReadScale.enabled.value,
        #                                         DatabaseReadScale.disabled.value,
        #                                         return_label=True))

        c.argument('zone_redundant',
                   arg_type=zone_redundant_param_type)

        c.argument('tier',
                   arg_type=tier_param_type,
                   help='The edition component of the sku. Allowed values include: Basic, Standard, '
                   'Premium, GeneralPurpose, BusinessCritical.')

        c.argument('capacity',
                   arg_type=capacity_param_type,
                   arg_group=sku_component_arg_group,
                   help='The capacity component of the sku in integer number of DTUs or vcores.')

        c.argument('family',
                   arg_type=family_param_type,
                   help='The compute generation component of the sku (for vcore skus only). '
                   'Allowed values include: Gen4, Gen5.')

    with self.argument_context('sql db create') as c:
        _configure_db_create_params(c, Engine.db, CreateMode.default)

    with self.argument_context('sql db copy') as c:
        _configure_db_create_params(c, Engine.db, CreateMode.copy)

        c.argument('dest_name',
                   help='Name of the database that will be created as the copy destination.')

        c.argument('dest_resource_group_name',
                   options_list=['--dest-resource-group'],
                   help='Name of the resouce group to create the copy in.'
                   ' If unspecified, defaults to the origin resource group.')

        c.argument('dest_server_name',
                   options_list=['--dest-server'],
                   help='Name of the server to create the copy in.'
                   ' If unspecified, defaults to the origin server.')

    with self.argument_context('sql db rename') as c:
        c.argument('new_name',
                   help='The new name that the database will be renamed to.')

    with self.argument_context('sql db restore') as c:
        _configure_db_create_params(c, Engine.db, CreateMode.point_in_time_restore)

        c.argument('dest_name',
                   help='Name of the database that will be created as the restore destination.')

        restore_point_arg_group = 'Restore Point'

        c.argument('restore_point_in_time',
                   options_list=['--time', '-t'],
                   arg_group=restore_point_arg_group,
                   help='The point in time of the source database that will be restored to create the'
                   ' new database. Must be greater than or equal to the source database\'s'
                   ' earliestRestoreDate value. Either --time or --deleted-time (or both) must be specified.')

        c.argument('source_database_deletion_date',
                   options_list=['--deleted-time'],
                   arg_group=restore_point_arg_group,
                   help='If specified, restore from a deleted database instead of from an existing database.'
                   ' Must match the deleted time of a deleted database in the same server.'
                   ' Either --time or --deleted-time (or both) must be specified.')

    with self.argument_context('sql db show') as c:
        # Service tier advisors and transparent data encryption are not included in the first batch
        # of GA commands.
        c.ignore('expand')

    with self.argument_context('sql db list') as c:
        c.argument('elastic_pool_name',
                   options_list=['--elastic-pool'],
                   help='If specified, lists only the databases in this elastic pool')

    with self.argument_context('sql db list-editions') as c:
        c.argument('show_details',
                   options_list=['--show-details', '-d'],
                   help='List of additional details to include in output.',
                   nargs='+',
                   arg_type=get_enum_type(DatabaseCapabilitiesAdditionalDetails))

        c.argument('available', arg_type=available_param_type)

        search_arg_group = 'Search'

        # We could used get_enum_type here, but that will validate the inputs which means there
        # will be no way to query for new editions/service objectives that are made available after
        # this version of CLI is released.
        c.argument('edition',
                   arg_type=tier_param_type,
                   arg_group=search_arg_group,
                   help='Edition to search for. If unspecified, all editions are shown.')

        c.argument('service_objective',
                   arg_group=search_arg_group,
                   help='Service objective to search for. If unspecified, all service objectives are shown.')

        c.argument('dtu',
                   arg_group=search_arg_group,
                   help='Number of DTUs to search for. If unspecified, all DTU sizes are shown.')

        c.argument('vcores',
                   arg_group=search_arg_group,
                   help='Number of vcores to search for. If unspecified, all vcore sizes are shown.')

    with self.argument_context('sql db update') as c:
        c.argument('service_objective',
                   arg_group=sku_arg_group,
                   help='The name of the new service objective. If this is a standalone db service'
                   ' objective and the db is currently in an elastic pool, then the db is removed from'
                   ' the pool.')

        c.argument('elastic_pool_id',
                   arg_type=elastic_pool_id_param_type,
                   help='The name or resource id of the elastic pool to move the database into.')

        c.argument('max_size_bytes', help='The new maximum size of the database expressed in bytes.')

        c.argument('compute_model',
                   arg_type=compute_model_param_type)

        c.argument('auto_pause_delay',
                   arg_type=auto_pause_delay_param_type)

        c.argument('min_capacity',
                   arg_type=min_capacity_param_type)

    with self.argument_context('sql db export') as c:
        # Create args that will be used to build up the ExportRequest object
        create_args_for_complex_type(
            c, 'parameters', ExportRequest, [
                'administrator_login',
                'administrator_login_password',
                'authentication_type',
                'storage_key',
                'storage_key_type',
                'storage_uri',
            ])

        c.argument('administrator_login',
                   options_list=['--admin-user', '-u'])

        c.argument('administrator_login_password',
                   options_list=['--admin-password', '-p'])

        c.argument('authentication_type',
                   options_list=['--auth-type', '-a'],
                   arg_type=get_enum_type(AuthenticationType))

        c.argument('storage_key_type',
                   arg_type=get_enum_type(StorageKeyType))

    with self.argument_context('sql db import') as c:
        # Create args that will be used to build up the ImportExtensionRequest object
        create_args_for_complex_type(c, 'parameters', ImportExtensionRequest, [
            'administrator_login',
            'administrator_login_password',
            'authentication_type',
            'storage_key',
            'storage_key_type',
            'storage_uri'
        ])

        c.argument('administrator_login',
                   options_list=['--admin-user', '-u'])

        c.argument('administrator_login_password',
                   options_list=['--admin-password', '-p'])

        c.argument('authentication_type',
                   options_list=['--auth-type', '-a'],
                   arg_type=get_enum_type(AuthenticationType))

        c.argument('storage_key_type',
                   arg_type=get_enum_type(StorageKeyType))

        # The parameter name '--name' is used for 'database_name', so we need to give a different name
        # for the import extension 'name' parameter to avoid conflicts. This parameter is actually not
        # needed, but we still need to avoid this conflict.
        c.argument('name', options_list=['--not-name'], arg_type=ignore_type)

    with self.argument_context('sql db show-connection-string') as c:
        c.argument('client_provider',
                   options_list=['--client', '-c'],
                   help='Type of client connection provider.',
                   arg_type=get_enum_type(ClientType))

        auth_group = 'Authentication'

        c.argument('auth_type',
                   options_list=['--auth-type', '-a'],
                   arg_group=auth_group,
                   help='Type of authentication.',
                   arg_type=get_enum_type(ClientAuthenticationType))

    #####
    #           sql db op
    #####
    with self.argument_context('sql db op') as c:
        c.argument('database_name',
                   options_list=['--database', '-d'],
                   required=True,
                   help='Name of the Azure SQL Database.')

        c.argument('operation_id',
                   options_list=['--name', '-n'],
                   required=True,
                   help='The unique name of the operation to cancel.')

    #####
    #           sql db replica
    #####
    with self.argument_context('sql db replica create') as c:
        _configure_db_create_params(c, Engine.db, CreateMode.secondary)

        c.argument('partner_resource_group_name',
                   options_list=['--partner-resource-group'],
                   help='Name of the resource group to create the new replica in.'
                   ' If unspecified, defaults to the origin resource group.')

        c.argument('partner_server_name',
                   options_list=['--partner-server'],
                   help='Name of the server to create the new replica in.')

    with self.argument_context('sql db replica set-primary') as c:
        c.argument('database_name',
                   help='Name of the database to fail over.')

        c.argument('server_name',
                   help='Name of the server containing the secondary replica that will become'
                   ' the new primary. ' + server_configure_help)

        c.argument('resource_group_name',
                   help='Name of the resource group containing the secondary replica that'
                   ' will become the new primary.')

    with self.argument_context('sql db replica delete-link') as c:
        c.argument('partner_server_name',
                   options_list=['--partner-server'],
                   help='Name of the server that the other replica is in.')

        c.argument('partner_resource_group_name',
                   options_list=['--partner-resource-group'],
                   help='Name of the resource group that the other replica is in. If unspecified,'
                   ' defaults to the first database\'s resource group.')

    #####
    #           sql db audit-policy & threat-policy
    #####
    def _configure_security_policy_storage_params(arg_ctx):
        storage_arg_group = 'Storage'

        arg_ctx.argument('storage_account',
                         options_list=['--storage-account'],
                         arg_group=storage_arg_group,
                         help='Name of the storage account.')

        arg_ctx.argument('storage_account_access_key',
                         options_list=['--storage-key'],
                         arg_group=storage_arg_group,
                         help='Access key for the storage account.')

        arg_ctx.argument('storage_endpoint',
                         arg_group=storage_arg_group,
                         help='The storage account endpoint.')

    with self.argument_context('sql db audit-policy update') as c:
        _configure_security_policy_storage_params(c)

        policy_arg_group = 'Policy'

        c.argument('state',
                   arg_group=policy_arg_group,
                   help='Auditing policy state',
                   arg_type=get_enum_type(BlobAuditingPolicyState))

        c.argument('audit_actions_and_groups',
                   options_list=['--actions'],
                   arg_group=policy_arg_group,
                   help='List of actions and action groups to audit.',
                   nargs='+')

        c.argument('retention_days',
                   arg_group=policy_arg_group,
                   help='The number of days to retain audit logs.')

    with self.argument_context('sql db threat-policy update') as c:
        _configure_security_policy_storage_params(c)

        policy_arg_group = 'Policy'
        notification_arg_group = 'Notification'

        c.argument('state',
                   arg_group=policy_arg_group,
                   help='Threat detection policy state',
                   arg_type=get_enum_type(SecurityAlertPolicyState))

        c.argument('retention_days',
                   arg_group=policy_arg_group,
                   help='The number of days to retain threat detection logs.')

        c.argument('disabled_alerts',
                   arg_group=policy_arg_group,
                   options_list=['--disabled-alerts'],
                   help='List of disabled alerts.',
                   nargs='+')

        c.argument('email_addresses',
                   arg_group=notification_arg_group,
                   options_list=['--email-addresses'],
                   help='List of email addresses that alerts are sent to.',
                   nargs='+')

        c.argument('email_account_admins',
                   arg_group=notification_arg_group,
                   options_list=['--email-account-admins'],
                   help='Whether the alert is sent to the account administrators.',
                   arg_type=get_enum_type(SecurityAlertPolicyEmailAccountAdmins))

        # TODO: use server default

    #####
    #           sql db transparent-data-encryption
    #####
    with self.argument_context('sql db tde') as c:
        c.argument('database_name',
                   options_list=['--database', '-d'],
                   required=True,
                   help='Name of the Azure SQL Database.')

    with self.argument_context('sql db tde set') as c:
        c.argument('status',
                   options_list=['--status'],
                   required=True,
                   help='Status of the transparent data encryption.',
                   arg_type=get_enum_type(TransparentDataEncryptionStatus))

    ###############################################
    #                sql dw                       #
    ###############################################
    with self.argument_context('sql dw') as c:
        c.argument('server_name',
                   arg_type=server_param_type)

        c.argument('database_name',
                   options_list=['--name', '-n'],
                   help='Name of the data warehouse.',
                   # Allow --ids command line argument. id_part=child_name_1 is 2nd name in uri
                   id_part='child_name_1')

        c.argument('max_size_bytes',
                   arg_type=max_size_bytes_param_type)

        c.argument('service_objective',
                   help='The service objective of the data warehouse. For example: ' +
                   dw_service_objective_examples)

        c.argument('collation',
                   help='The collation of the data warehouse.')

    with self.argument_context('sql dw create') as c:
        _configure_db_create_params(c, Engine.dw, CreateMode.default)

    with self.argument_context('sql dw show') as c:
        # Service tier advisors and transparent data encryption are not included in the first batch
        # of GA commands.
        c.ignore('expand')

    # Data Warehouse restore will not be included in the first batch of GA commands
    # (list_restore_points also applies to db, but it's not very useful. It's
    # mainly useful for dw.)
    # with ParametersContext(command='sql dw restore-point') as c:
    #     c.register_alias('database_name', ('--database', '-d'))

    ###############################################
    #                sql elastic-pool             #
    ###############################################
    with self.argument_context('sql elastic-pool') as c:
        c.argument('server_name',
                   arg_type=server_param_type)

        c.argument('elastic_pool_name',
                   options_list=['--name', '-n'],
                   help='The name of the elastic pool.',
                   # Allow --ids command line argument. id_part=child_name_1 is 2nd name in uri
                   id_part='child_name_1')

        # --db-dtu-max and --db-dtu-min were the original param names, which is consistent with the
        # 2014-04-01 REST API.
        # --db-max-dtu and --db-min-dtu are aliases which are consistent with the `sql elastic-pool
        # list-editions --show-details db-max-dtu db-min-dtu` parameter values. These are more
        # consistent with other az sql commands, but the original can't be removed due to
        # compatibility.
        c.argument('max_capacity',
                   options_list=['--db-dtu-max', '--db-max-dtu', '--db-max-capacity'],
                   help='The maximum capacity (in DTUs or vcores) any one database can consume.')

        c.argument('min_capacity',
                   options_list=['--db-dtu-min', '--db-min-dtu', '--db-min-capacity'],
                   help='The minumum capacity (in DTUs or vcores) each database is guaranteed.')

        # --storage was the original param name, which is consistent with the underlying REST API.
        # --max-size is an alias which is consistent with the `sql elastic-pool list-editions
        # --show-details max-size` parameter value and also matches `sql db --max-size` parameter name.
        c.argument('max_size_bytes',
                   arg_type=max_size_bytes_param_type,
                   options_list=['--max-size', '--storage'])

        c.argument('license_type',
                   arg_type=get_enum_type(ElasticPoolLicenseType))

        c.argument('zone_redundant',
                   arg_type=zone_redundant_param_type)

        c.argument('tier',
                   arg_type=tier_param_type,
                   help='The edition component of the sku. Allowed values include: Basic, Standard, '
                   'Premium, GeneralPurpose, BusinessCritical.')

        c.argument('capacity',
                   arg_type=capacity_or_dtu_param_type,
                   help='The capacity component of the sku in integer number of DTUs or vcores.')

        c.argument('family',
                   arg_type=family_param_type,
                   help='The compute generation component of the sku (for vcore skus only). '
                   'Allowed values include: Gen4, Gen5.')

    with self.argument_context('sql elastic-pool create') as c:
        # Create args that will be used to build up the ElasticPool object
        create_args_for_complex_type(
            c, 'parameters', ElasticPool, [
                'license_type',
                'max_size_bytes',
                'name',
                'per_database_settings',
                'tags',
                'zone_redundant',
            ])

        # Create args that will be used to build up the ElasticPoolPerDatabaseSettings object
        create_args_for_complex_type(
            c, 'per_database_settings', ElasticPoolPerDatabaseSettings, [
                'max_capacity',
                'min_capacity',
            ])

        # Create args that will be used to build up the ElasticPool Sku object
        create_args_for_complex_type(
            c, 'sku', Sku, [
                'capacity',
                'family',
                'name',
                'tier',
            ])

        c.ignore('name')  # Hide sku name

    with self.argument_context('sql elastic-pool list-editions') as c:
        # Note that `ElasticPoolCapabilitiesAdditionalDetails` intentionally match param names to
        # other commands, such as `sql elastic-pool create --db-max-dtu --db-min-dtu --max-size`.
        c.argument('show_details',
                   options_list=['--show-details', '-d'],
                   help='List of additional details to include in output.',
                   nargs='+',
                   arg_type=get_enum_type(ElasticPoolCapabilitiesAdditionalDetails))

        c.argument('available',
                   arg_type=available_param_type)

        search_arg_group = 'Search'

        # We could used 'arg_type=get_enum_type' here, but that will validate the inputs which means there
        # will be no way to query for new editions that are made available after
        # this version of CLI is released.
        c.argument('edition',
                   arg_type=tier_param_type,
                   arg_group=search_arg_group,
                   help='Edition to search for. If unspecified, all editions are shown.')

        c.argument('dtu',
                   arg_group=search_arg_group,
                   help='Number of DTUs to search for. If unspecified, all DTU sizes are shown.')

        c.argument('vcores',
                   arg_group=search_arg_group,
                   help='Number of vcores to search for. If unspecified, all vcore sizes are shown.')

    with self.argument_context('sql elastic-pool update') as c:
        c.argument('database_dtu_max',
                   help='The maximum DTU any one database can consume.')

        c.argument('database_dtu_min',
                   help='The minimum DTU all databases are guaranteed.')

        c.argument('storage_mb',
                   help='Storage limit for the elastic pool in MB.')

    #####
    #           sql elastic-pool op
    #####
    with self.argument_context('sql elastic-pool op') as c:
        c.argument('elastic_pool_name',
                   options_list=['--elastic-pool'],
                   help='Name of the Azure SQL Elastic Pool.')

        c.argument('operation_id',
                   options_list=['--name', '-n'],
                   help='The unique name of the operation to cancel.')

    ###############################################
    #             sql failover-group              #
    ###############################################

    with self.argument_context('sql failover-group') as c:
        c.argument('failover_group_name', options_list=['--name', '-n'], help="The name of the Failover Group")
        c.argument('server_name', arg_type=server_param_type)
        c.argument('partner_server', help="The name of the partner server of a Failover Group")
        c.argument('partner_resource_group', help="The name of the resource group of the partner server")
        c.argument('failover_policy', help="The failover policy of the Failover Group",
                   arg_type=get_enum_type(FailoverPolicyType))
        c.argument('grace_period',
                   arg_type=grace_period_param_type)
        c.argument('add_db', nargs='+',
                   help='List of databases to add to Failover Group')
        c.argument('remove_db', nargs='+',
                   help='List of databases to remove from Failover Group')
        c.argument('allow_data_loss',
                   arg_type=allow_data_loss_param_type)

    ###############################################
    #                sql server                   #
    ###############################################
    with self.argument_context('sql server') as c:
        c.argument('server_name',
                   arg_type=server_param_type,
                   options_list=['--name', '-n'])

        c.argument('administrator_login',
                   options_list=['--admin-user', '-u'])

        c.argument('administrator_login_password',
                   options_list=['--admin-password', '-p'])

        c.argument('assign_identity',
                   options_list=['--assign_identity', '-i'],
                   help='Generate and assign an Azure Active Directory Identity for this server'
                   'for use with key management services like Azure KeyVault.')

    with self.argument_context('sql server create') as c:
        c.argument('location',
                   arg_type=get_location_type_with_default_from_resource_group(self.cli_ctx))

        # Create args that will be used to build up the Server object
        create_args_for_complex_type(
            c, 'parameters', Server, [
                'administrator_login',
                'administrator_login_password',
                'location'
            ])

        c.argument('administrator_login',
                   required=True)

        c.argument('administrator_login_password',
                   required=True)

        c.argument('assign_identity',
                   options_list=['--assign-identity', '-i'],
                   help='Generate and assign an Azure Active Directory Identity for this server'
                   'for use with key management services like Azure KeyVault.')

    with self.argument_context('sql server update') as c:
        c.argument('administrator_login_password',
                   help='The administrator login password.')

    #####
    #           sql server ad-admin
    ######
    with self.argument_context('sql server ad-admin') as c:
        # The options list should be ['--server', '-s'], but in the originally released version it was
        # ['--server-name'] which we must keep for backward compatibility - but we should deprecate it.
        c.argument('server_name',
                   options_list=['--server-name', '--server', '-s'])

        c.argument('login',
                   arg_type=aad_admin_login_param_type)

        c.argument('sid',
                   arg_type=aad_admin_sid_param_type)

        c.ignore('tenant_id')

    with self.argument_context('sql server ad-admin create') as c:
        # Create args that will be used to build up the ServerAzureADAdministrator object
        create_args_for_complex_type(
            c, 'properties', ServerAzureADAdministrator, [
                'login',
                'sid',
            ])

    #####
    #           sql server conn-policy
    #####
    with self.argument_context('sql server conn-policy') as c:
        c.argument('server_name',
                   arg_type=server_param_type)

        c.argument('connection_type',
                   options_list=['--connection-type', '-t'],
                   arg_type=get_enum_type(ServerConnectionType))

    #####
    #           sql server dns-alias
    #####
    with self.argument_context('sql server dns-alias') as c:
        c.argument('server_name',
                   arg_type=server_param_type)

        c.argument('dns_alias_name',
                   options_list=('--name', '-n'),
                   help='Name of the DNS alias.')

        c.argument('original_server_name',
                   options_list=('--original-server'),
                   help='The name of the server to which alias is currently pointing')

        c.argument('original_resource_group_name',
                   options_list=('--original-resource-group'),
                   help='Name of the original resource group.')

        c.argument('original_subscription_id',
                   options_list=('--original-subscription-id'),
                   help='ID of the original subscription.')

    #####
    #           sql server firewall-rule
    #####
    with self.argument_context('sql server firewall-rule') as c:
        # Help text needs to be specified because 'sql server firewall-rule update' is a custom
        # command.
        c.argument('server_name',
                   arg_type=server_param_type)

        c.argument('firewall_rule_name',
                   options_list=['--name', '-n'],
                   help='The name of the firewall rule.',
                   # Allow --ids command line argument. id_part=child_name_1 is 2nd name in uri
                   id_part='child_name_1')

        c.argument('start_ip_address',
                   options_list=['--start-ip-address'],
                   help='The start IP address of the firewall rule. Must be IPv4 format. Use value'
                   ' \'0.0.0.0\' to represent all Azure-internal IP addresses.')

        c.argument('end_ip_address',
                   options_list=['--end-ip-address'],
                   help='The end IP address of the firewall rule. Must be IPv4 format. Use value'
                   ' \'0.0.0.0\' to represent all Azure-internal IP addresses.')

    #####
    #           sql server key
    #####
    with self.argument_context('sql server key') as c:
        c.argument('server_name',
                   arg_type=server_param_type)

        c.argument('key_name',
                   options_list=['--name', '-n'])

        c.argument('kid',
                   arg_type=kid_param_type,
                   required=True)

    #####
    #           sql server tde-key
    #####
    with self.argument_context('sql server tde-key') as c:
        c.argument('server_name',
                   arg_type=server_param_type)

    with self.argument_context('sql server tde-key set') as c:
        c.argument('kid',
                   arg_type=kid_param_type)

        c.argument('server_key_type',
                   arg_type=server_key_type_param_type)

    #####
    #           sql server vnet-rule
    #####
    with self.argument_context('sql server vnet-rule') as c:
        # Help text needs to be specified because 'sql server vnet-rule create' is a custom
        # command.
        c.argument('server_name',
                   arg_type=server_param_type)

        c.argument('virtual_network_rule_name',
                   options_list=['--name', '-n'])

        c.argument('virtual_network_subnet_id',
                   options_list=['--subnet'],
                   help='Name or ID of the subnet that allows access to an Azure Sql Server. '
                   'If subnet name is provided, --vnet-name must be provided.')

        c.argument('ignore_missing_vnet_service_endpoint',
                   options_list=['--ignore-missing-endpoint', '-i'],
                   help='Create firewall rule before the virtual network has vnet service endpoint enabled',
                   arg_type=get_three_state_flag())

    with self.argument_context('sql server vnet-rule create') as c:
        c.extra('vnet_name',
                options_list=['--vnet-name'],
                help='The virtual network name')

    ###############################################
    #                sql managed instance         #
    ###############################################
    with self.argument_context('sql mi') as c:
        c.argument('managed_instance_name',
                   help='The managed instance name',
                   options_list=['--name', '-n'],
                   # Allow --ids command line argument. id_part=name is 1st name in uri
                   id_part='name')

        c.argument('tier',
                   arg_type=tier_param_type,
                   help='The edition component of the sku. Allowed values: GeneralPurpose, BusinessCritical.')

        c.argument('family',
                   arg_type=family_param_type,
                   help='The compute generation component of the sku. '
                   'Allowed values include: Gen4, Gen5.')

        c.argument('storage_size_in_gb',
                   options_list=['--storage'],
                   arg_type=storage_param_type,
                   help='The storage size of the managed instance. '
                   'Storage size must be specified in increments of 32 GB')

        c.argument('license_type',
                   arg_type=get_enum_type(DatabaseLicenseType),
                   help='The license type to apply for this managed instance.')

        c.argument('vcores',
                   arg_type=capacity_param_type,
                   help='The capacity of the managed instance in vcores.')

        c.argument('collation',
                   help='The collation of the managed instance.')

        c.argument('proxy_override',
                   arg_type=get_enum_type(ServerConnectionType),
                   help='The connection type used for connecting to the instance.')

        c.argument('public_data_endpoint_enabled',
                   arg_type=get_three_state_flag(),
                   help='Whether or not the public data endpoint is enabled for the instance.')

        c.argument('timezone_id',
                   help='The time zone id for the instance to set. '
                   'A list of time zone ids is exposed through the sys.time_zone_info (Transact-SQL) view.')

    with self.argument_context('sql mi create') as c:
        c.argument('location',
                   arg_type=get_location_type_with_default_from_resource_group(self.cli_ctx))

        # Create args that will be used to build up the ManagedInstance object
        create_args_for_complex_type(
            c, 'parameters', ManagedInstance, [
                'administrator_login',
                'administrator_login_password',
                'license_type',
                'virtual_network_subnet_id',
                'vcores',
                'storage_size_in_gb',
                'collation',
                'proxy_override',
                'public_data_endpoint_enabled',
                'timezone_id',
            ])

        # Create args that will be used to build up the Managed Instance's Sku object
        create_args_for_complex_type(
            c, 'sku', Sku, [
                'family',
                'name',
                'tier',
            ])

        c.ignore('name')  # Hide sku name

        c.argument('administrator_login',
                   options_list=['--admin-user', '-u'],
                   required=True)

        c.argument('administrator_login_password',
                   options_list=['--admin-password', '-p'],
                   required=True)

        c.extra('vnet_name',
                options_list=['--vnet-name'],
                help='The virtual network name',
                validator=validate_subnet)

        c.argument('virtual_network_subnet_id',
                   options_list=['--subnet'],
                   required=True,
                   help='Name or ID of the subnet that allows access to an Azure Sql Managed Instance. '
                   'If subnet name is provided, --vnet-name must be provided.')

        c.argument('assign_identity',
                   options_list=['--assign-identity', '-i'],
                   help='Generate and assign an Azure Active Directory Identity for this managed instance '
                   'for use with key management services like Azure KeyVault.')

    with self.argument_context('sql mi update') as c:
        # Create args that will be used to build up the ManagedInstance object
        create_args_for_complex_type(
            c, 'parameters', ManagedInstance, [
                'administrator_login_password',
            ])

        c.argument('administrator_login_password',
                   options_list=['--admin-password', '-p'])

        c.argument('assign_identity',
                   options_list=['--assign-identity', '-i'],
                   help='Generate and assign an Azure Active Directory Identity for this managed instance '
                   'for use with key management services like Azure KeyVault. '
                   'If identity is already assigned - do nothing.')

    #####
    #           sql managed instance key
    #####
    with self.argument_context('sql mi key') as c:
        c.argument('managed_instance_name',
                   arg_type=managed_instance_param_type)

        c.argument('key_name',
                   options_list=['--name', '-n'])

        c.argument('kid',
                   arg_type=kid_param_type,
                   required=True,)

    #####
    #           sql managed instance ad-admin
    ######
    with self.argument_context('sql mi ad-admin') as c:
        c.argument('managed_instance_name',
                   arg_type=managed_instance_param_type)

        c.argument('login',
                   arg_type=aad_admin_login_param_type)

        c.argument('sid',
                   arg_type=aad_admin_sid_param_type)

    with self.argument_context('sql mi ad-admin create') as c:
        # Create args that will be used to build up the ManagedInstanceAdministrator object
        create_args_for_complex_type(
            c, 'properties', ManagedInstanceAdministrator, [
                'login',
                'sid',
            ])

    with self.argument_context('sql mi ad-admin update') as c:
        # Create args that will be used to build up the ManagedInstanceAdministrator object
        create_args_for_complex_type(
            c, 'properties', ManagedInstanceAdministrator, [
                'login',
                'sid',
            ])

    #####
    #           sql server tde-key
    #####
    with self.argument_context('sql mi tde-key') as c:
        c.argument('managed_instance_name',
                   arg_type=managed_instance_param_type)

    with self.argument_context('sql mi tde-key set') as c:
        c.argument('kid',
                   arg_type=kid_param_type)

        c.argument('server_key_type',
                   arg_type=server_key_type_param_type)

    ###############################################
    #                sql managed db               #
    ###############################################
    with self.argument_context('sql midb') as c:
        c.argument('managed_instance_name',
                   arg_type=managed_instance_param_type,
                   # Allow --ids command line argument. id_part=name is 1st name in uri
                   id_part='name')

        c.argument('database_name',
                   options_list=['--name', '-n'],
                   help='The name of the Azure SQL Managed Database.',
                   # Allow --ids command line argument. id_part=child_name_1 is 2nd name in uri
                   id_part='child_name_1')

    with self.argument_context('sql midb create') as c:
        create_args_for_complex_type(
            c, 'parameters', ManagedDatabase, [
                'collation',
            ])

        c.argument('collation',
                   required=False,
                   help='The collation of the Azure SQL Managed Database collation to use, '
                   'e.g.: SQL_Latin1_General_CP1_CI_AS or Latin1_General_100_CS_AS_SC')

    with self.argument_context('sql midb restore') as c:
        create_args_for_complex_type(
            c, 'parameters', ManagedDatabase, [
                'target_managed_database_name',
                'target_managed_instance_name',
                'restore_point_in_time'
            ])

        c.argument('target_managed_database_name',
                   options_list=['--dest-name'],
                   required=True,
                   help='Name of the managed database that will be created as the restore destination.')

        c.argument('target_managed_instance_name',
                   options_list=['--dest-mi'],
                   help='Name of the managed instance to restore managed database to. '
                   'This can be same managed instance, or another managed instance on same subscription. '
                   'When not specified it defaults to source managed instance.')

        c.argument('target_resource_group_name',
                   options_list=['--dest-resource-group'],
                   help='Name of the resource group of the managed instance to restore managed database to. '
                   'When not specified it defaults to source resource group.')

        restore_point_arg_group = 'Restore Point'

        c.argument('restore_point_in_time',
                   options_list=['--time', '-t'],
                   arg_group=restore_point_arg_group,
                   required=True,
                   help='The point in time of the source database that will be restored to create the'
                   ' new database. Must be greater than or equal to the source database\'s'
                   ' earliestRestoreDate value. Time should be in following format: "YYYY-MM-DDTHH:MM:SS"')

    with self.argument_context('sql midb list') as c:
        c.argument('managed_instance_name', id_part=None)

    ###############################################
    #                sql virtual cluster          #
    ###############################################
    with self.argument_context('sql virtual-cluster') as c:
        c.argument('virtual_cluster_name',
                   help='The virtual cluster name',
                   options_list=['--name', '-n'],
                   # Allow --ids command line argument. id_part=name is 1st name in uri
                   id_part='name')

        c.argument('resource_group_name', arg_type=resource_group_name_type)

    ###############################################
    #             sql instance failover-group     #
    ###############################################

    with self.argument_context('sql instance-failover-group') as c:
        c.argument('failover_group_name',
                   options_list=['--name', '-n'],
                   help="The name of the Instance Failover Group")

        c.argument('managed_instance',
                   arg_type=managed_instance_param_type,
                   options_list=['--source-mi', '--mi'])

        c.argument('partner_managed_instance',
                   help="The name of the partner managed instance of a Instance Failover Group",
                   options_list=['--partner-mi'])

        c.argument('partner_resource_group',
                   help="The name of the resource group of the partner managed instance")

        c.argument('failover_policy',
                   help="The failover policy of the Instance Failover Group",
                   arg_type=get_enum_type(FailoverPolicyType))

        c.argument('grace_period',
                   arg_type=grace_period_param_type)

        c.argument('allow_data_loss',
                   arg_type=allow_data_loss_param_type)
