# LLM 演化速查表 (面试 5 分钟扫完)

> 用途：AI 应用/Agent/RAG 岗，面试官如果突然问"GPT 是怎么发展过来的"，能讲 1 分钟即可。**不需要懂数学**。

---

## 一、5 代演化 (一句话 / 代)

| 代际 | 年份 | 核心创新 (一句话) | 你已经在用的对应物 |
|---|---|---|---|
| **GPT-1** | 2018 | 第一次证明 **"预训练 + 微调"** 这套范式在 NLP 上能打 | 你用 bge-m3 做 embedding——就是 "预训练" 的活化石 |
| **GPT-2** | 2019 | 模型变大 (1.5B) + 不微调也能做下游任务 = **零样本** (zero-shot) | 你写 prompt 让 LLM 直接干活，没微调，就是 GPT-2 范式 |
| **GPT-3** | 2020 | 175B 参数 + **few-shot / in-context learning**：给几个例子就能学 | 你在 prompt 里塞 3 个示例让它照着输出——这就是 in-context learning |
| **InstructGPT** | 2022 | 引入 **RLHF** (人类反馈强化学习) 对齐人类偏好 | 你用的所有"听话的"商业大模型 (Claude, GPT-4) 都做了这一步 |
| **ChatGPT** | 2022.11 | InstructGPT + 对话格式 + 产品化 = 出圈 | 你每天调的 chat API，user/assistant/system 三角色就是它定的 |

---

## 二、面试必背 5 行 (一字不改照背)

1. **GPT-1 是预训练+微调的奠基**，证明了 Transformer Decoder 路线可行。
2. **GPT-2 把模型做大，发现了 zero-shot 能力**——不微调也能写文章。
3. **GPT-3 又大了 100 倍，涌现出 in-context learning**——这是 Prompt Engineering 的理论起点。
4. **InstructGPT 用 RLHF 解决了"模型听不听话"问题**——SFT + RM + PPO 三步走。
5. **ChatGPT = InstructGPT 套上对话外壳**，2022.11 出圈，今天所有 chat 模型都是它的后代。

---

## 三、被问到时的标准应答模板

> "GPT 系列大致经历了 5 个阶段：GPT-1 奠定预训练+微调范式，GPT-2 发现了 zero-shot，GPT-3 又把规模拉大涌现了 in-context learning，InstructGPT 引入 RLHF 解决对齐问题，ChatGPT 是 InstructGPT 的对话产品化。我做 ai_collector_project 时主要在用 GPT-3 之后的能力——in-context learning 写 prompt，加上对齐后的指令跟随。"

(说完就停，别展开 Transformer 数学，那不是这岗位的事。)

---

## 四、AI 应用岗 **不会问** 的 (放心跳过)

- ❌ Transformer 注意力公式 / Q K V 怎么算
- ❌ GPT-1 用了几层 Decoder
- ❌ RLHF 的 PPO 损失函数
- ❌ Tokenizer BPE 怎么训
- ❌ 各代具体训练数据集大小

如果面试官真问到这些，那是算法岗，不是你的目标。礼貌承认"我主要做应用侧，底层细节没深挖"就行——比胡编强。

---

## 五、跟你 ai_collector_project 的连接

你已经在用的能力，对应 GPT 哪一代：
- `langchain.chat_models` 调 GPT/Claude → InstructGPT + ChatGPT 范式
- prompt 里写"你是一个 JD 解析助手，请按 JSON 格式返回..." → GPT-3 in-context learning
- bge-m3 做向量化 → GPT-1 预训练思想 (虽然 bge 是 BERT 系，但同源)
- 你完全没碰过的 → RLHF 微调 (这是训练侧的事，应用岗不要求)

**结论**：你做 v3.0 Agent，已经在 GPT-3 之后的层级了。回头啃 GPT-1 论文细节，对你近期面试没收益。

---

_2026-06-28 张敏杰 · 跳过阶段13/day_01 13集纯理论后的 5 分钟替代品_
