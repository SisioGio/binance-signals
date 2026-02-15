#!/usr/bin/env python3
import aws_cdk as cdk
from trading_stack import MyTradingBotStack

app = cdk.App()
MyTradingBotStack(app, "MyTradingBotStack")
app.synth()
