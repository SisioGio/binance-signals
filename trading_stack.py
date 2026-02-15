from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_secretsmanager as secretsmanager
)
from constructs import Construct

class MyTradingBotStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        secret_name = 'TRADING_SECRETS'
        secret = secretsmanager.Secret.from_secret_name_v2(
            self, "TradingSecret",
            secret_name=secret_name
        )
        
        utils_1_layer = _lambda.LayerVersion(
            self, "TradingUtilsLayer",
            code=_lambda.Code.from_asset("layer/utils_1"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            description="Trading utils"
        )
        
        utils_2_layer = _lambda.LayerVersion(
            self, "TradingUtilsLayer",
            code=_lambda.Code.from_asset("layer/utils_2"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            description="Trading utils"
        )
        
        
        # ===== LAMBDA FUNCTION =====
        bot_lambda = _lambda.Function(
            self, "TradingBotLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.main",
            code=_lambda.Code.from_asset("src/binance"),
            timeout=Duration.seconds(10),
            memory_size=512,
            environment={
                "SECRET_NAME": secret_name
            },
            layers=[utils_1_layer,utils_2_layer]
        )

        # Allow Lambda to read secret
        secret.grant_read(bot_lambda)

        # ===== CLOUDWATCH EVENT: EVERY MINUTE =====
        rule = events.Rule(
            self, "TradingBotSchedule",
            schedule=events.Schedule.rate(Duration.minutes(1))
        )

        rule.add_target(targets.LambdaFunction(bot_lambda))
