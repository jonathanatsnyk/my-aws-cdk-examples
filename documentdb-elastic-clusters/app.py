#!/usr/bin/env python3
import os
import json

from cdk_stacks import (
  VpcStack,
  DocDBClientEC2InstanceStack
)

import aws_cdk as cdk

from aws_cdk import (
  Stack,
  aws_docdbelastic,
  aws_ec2,
  aws_secretsmanager
)
from constructs import Construct


class DocumentDbElasticClustersStack(Stack):
  def __init__(self, scope: Construct, construct_id: str, vpc, **kwargs) -> None:
    super().__init__(scope, construct_id, **kwargs)

    sg_docdb_client = aws_ec2.SecurityGroup(self, 'DocDBClientSG',
      vpc=vpc,
      allow_all_outbound=True,
      description='security group for documentdb elastic clusters client',
      security_group_name='docdb-elastic-client-sg'
    )
    cdk.Tags.of(sg_docdb_client).add('Name', 'docdbelastic-client-sg')

    sg_docdb_server = aws_ec2.SecurityGroup(self, 'DocDBServerSG',
      vpc=vpc,
      allow_all_outbound=True,
      description='security group for documentdb elastic clusters',
      security_group_name='docdb-elastic-cluster-sg'
    )
    sg_docdb_server.add_ingress_rule(peer=sg_docdb_client, connection=aws_ec2.Port.tcp(27017),
      description='docdb-elastic-client-sg')
    cdk.Tags.of(sg_docdb_server).add('Name', 'docdbelastic-cluster-sg')

    docdb_cluster_name = self.node.try_get_context('docdb_cluster_name') or self.stack_name
    secret_name = self.node.try_get_context('docdb_cluster_secret_name')
    admin_user_secret = aws_secretsmanager.Secret.from_secret_name_v2(self,
      'DocDBElasticAdminUserSecret',
      secret_name)

    #XXX: If you want to create a new secret with a randomly generated password,
    # remove comments from the below codes and
    # comments out admin_user_secret = aws_secretsmanager.Secret.from_secret_name_v2(..) codes
    #
    # admin_user_secret = aws_secretsmanager.Secret(self, 'DocDBElasticAdminUserSecret',
    #   secret_name=secret_name,
    #   generate_secret_string=aws_secretsmanager.SecretStringGenerator(
    #     #XXX: DO NOT USE 'admin' as AdminUsername
    #     # AdminUsername 'admin' cannot be used as it is a reserved word used by the engine
    #     secret_string_template=json.dumps({"admin_user_name": "docdbadmin"}),
    #     generate_string_key="admin_user_password",
    #     # DocDBElastic AdminUserPassword Constraints:
    #     # - Must contain from 8 to 100 characters.
    #     # - Cannot contain a forward slash (/), double quote ("), or the "at" symbol (@).
    #     # - A valid AdminUserName entry is also required.
    #     exclude_characters='/"@',
    #     exclude_numbers=True,
    #     exclude_punctuation=True,
    #     password_length=8
    #   )
    # )

    docdb_cluster = aws_docdbelastic.CfnCluster(self, 'DocDBElasticCluster',
      admin_user_name=admin_user_secret.secret_value_from_json("admin_user_name").unsafe_unwrap(),
      admin_user_password=admin_user_secret.secret_value_from_json("admin_user_password").unsafe_unwrap(),
      auth_type='PLAIN_TEXT',
      cluster_name=docdb_cluster_name,
      shard_capacity=8, # Allowed values: [2, 4, 8, 16, 32, 64]
      shard_count=4, # The maximum number of shards per cluster: 32
      preferred_maintenance_window='sun:18:00-sun:18:30',
      subnet_ids=vpc.select_subnets(subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS).subnet_ids,
      vpc_security_group_ids=[sg_docdb_server.security_group_id]
    )
    docdb_cluster.apply_removal_policy(cdk.RemovalPolicy.RETAIN)

    self.sg_docdb_client = sg_docdb_client

    cdk.CfnOutput(self, f'{self.stack_name}-DocDbElasticClusterArn', value=docdb_cluster.attr_cluster_arn,
        export_name=f'{self.stack_name}-DocDbElasticClusterArn')


AWS_ENV = cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'),
  region=os.getenv('CDK_DEFAULT_REGION'))

app = cdk.App()

vpc_stack = VpcStack(app, 'DocDBElasticVpc',
  env=AWS_ENV)

docdb_elastic_cluster_stack = DocumentDbElasticClustersStack(app, 'DocDBElasticStack',
  vpc_stack.vpc
)
docdb_elastic_cluster_stack.add_dependency(vpc_stack)

docdb_client_ec2_stack = DocDBClientEC2InstanceStack(app, 'DocDBClientEC2Instance',
  vpc_stack.vpc,
  docdb_elastic_cluster_stack.sg_docdb_client
)
docdb_client_ec2_stack.add_dependency(docdb_elastic_cluster_stack)

app.synth()

