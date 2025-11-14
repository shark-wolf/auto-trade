import ccxt

# 打印CCXT版本和所有支持的交易所名称
print(f"CCXT 版本: {ccxt.__version__}")
print("支持的交易所列表:")
print(ccxt.exchanges)
print(f"\n总计支持 {len(ccxt.exchanges)} 家交易所")