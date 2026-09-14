from datetime import datetime
import uuid

from datetime import datetime
import uuid
import hashlib
import json

AUDIT = []

# 模拟区块链的当前全局高度（创世区块高度为 1）
CURRENT_BLOCK_NUMBER = 1
# 模拟每个区块最多容纳 3 笔交易，满了高度就 +1
TX_COUNTER_IN_BLOCK = 0
TX_PER_BLOCK = 3 

def calculate_mock_tx_hash(event_dict):
    """
    密码学计算：模拟区块链根据交易内容计算 TxHash 的过程
    将除了 event_id, timestamp, tx_hash, block_number 之外的核心交易数据进行哈希
    """
    # 提取核心交易要素
    core_data = {
        "actor_did": event_dict["actor_did"],
        "action": event_dict["action"],
        "patient_did": event_dict["patient_did"],
        "consent_id": event_dict["consent_id"],
        "result": event_dict["result"]
    }
    # 1. 序列化：将字典转换为严格排序的 JSON 字符串字符串（确保数据一致性）
    serialized_data = json.dumps(core_data, sort_keys=True).encode('utf-8')
    
    # 2. 哈希计算：使用 SHA-256 算法计算哈希
    hash_object = hashlib.sha256(serialized_data)
    
    # 3. 输出符合 EVM 规范的 0x 开头的十六进制字符串
    return "0x" + hash_object.hexdigest()


def log(
    actor_did,
    actor_role,
    action,
    patient_did,
    consent_id,
    scope=None,
    purpose=None,
    result="SUCCESS",
    metadata=None,
    # 默认留空，由内部逻辑动态计算和获取
    tx_hash=None,
    block_number=None
):
    global CURRENT_BLOCK_NUMBER, TX_COUNTER_IN_BLOCK
    
    # 1. 先构建基础的事件结构
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "actor_did": actor_did,
        "actor_role": actor_role,
        "action": action,
        "patient_did": patient_did,
        "consent_id": consent_id,
        "scope": scope,
        "purpose": purpose,
        "result": result,
        "metadata": metadata
    }
    
    # 2. 模拟计算 TxHash (如果没有显式传入)
    if tx_hash is None:
        tx_hash = calculate_mock_tx_hash(event)
    
    # 3. 模拟获取 Block Number (模拟区块打包打包逻辑)
    if block_number is None:
        block_number = CURRENT_BLOCK_NUMBER
        TX_COUNTER_IN_BLOCK += 1
        # 如果当前区块里的交易数达到了上限，下一个交易就进入下一个区块
        if TX_COUNTER_IN_BLOCK >= TX_PER_BLOCK:
            CURRENT_BLOCK_NUMBER += 1
            TX_COUNTER_IN_BLOCK = 0
            
    # 4. 将计算和获取好的字段装填入事件
    event["tx_hash"] = tx_hash
    event["block_number"] = block_number

    AUDIT.append(event)


def get():
    return AUDIT

# ====== 测试运行 ======
if __name__ == "__main__":
    # 连续写入 4 笔审计日志，观察 block_number 的自增和 tx_hash 的生成
    for i in range(4):
        log(
            actor_did=f"did:example:doctor{i}",
            actor_role="DOCTOR",
            action="ACCESS_HEALTH_RECORD",
            patient_did="did:example:patient999",
            consent_id=f"consent-uuid-111-222-{i}"
        )
        
    print(json.dumps(get(), indent=4))



# AUDIT=[]

# def log(
#     actor_did,
#     actor_role,
#     action,
#     patient_did,
#     consent_id,
#     scope=None,
#     purpose=None,
#     result="SUCCESS",
#     metadata=None,
#     tx_hash=None,
#     block_number=None
# ):

#     AUDIT.append(
#         {
#             "event_id":str(uuid.uuid4()),
#             "timestamp":datetime.now().isoformat(),
#             "actor_did":actor_did,
#             "actor_role":actor_role,
#             "action":action,
#             "patient_did":patient_did,
#             "consent_id":consent_id,
#             "scope":scope,
#             "purpose":purpose,
#             "result":result,
#             "tx_hash":tx_hash,
#             "block_number":block_number,
#             "metadata":metadata
#         }
#     )


# def get():
#     return AUDIT

