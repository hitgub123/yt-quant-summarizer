# 🎬 Let's build GPT: from scratch, in code, spelled out.

- **创作者**：`Andrej Karpathy` | **发布日期**：`2026-08-30` | **原视频链接**：[YouTube 视频](https://www.youtube.com/watch?v=kCc8FmEb1nY)

---

### 📌 一句话核心主旨 (TL;DR)
本视频通过 PyTorch 从零开始手写构建一个字符级（Character-level）的 GPT（Decoder-only Transformer）模型。Andrej 逐步编写并解析了自注意力机制、多头注意力、残差连接以及层归一化等核心组件，并成功在莎士比亚数据集上训练并生成了文本。

### 🔍 核心要点精炼拆解 (Key Takeaways)

1. **基线模型建立（Bigram Language Model）**
   * 从最简单的双字母（Bigram）模型起步，模型仅根据当前单个字符来预测下一个字符。通过此基线，帮助学习者理解 PyTorch 的 `nn.Embedding`、交叉熵损失计算以及生成（Generation）的基本流程。

2. **自注意力机制（Self-Attention）的数学与物理直觉**
   * **核心机制**：每个 Token 发射三个向量：**Query**（我在寻找什么）、**Key**（我包含什么信息）和 **Value**（如果选我，我能贡献什么）。
   * **注意力矩阵计算**：$Attention(Q, K, V) = \text{softmax}(\frac{QK^T}{\sqrt{d_k}})V$。通过对 $Q$ 和 $K$ 的点积计算相似度，并使用比例因子 $\sqrt{d_k}$ 缩放（防止 Softmax 梯度饱和）。
   * **因果遮蔽（Causal Masking）**：在 Decoder 中，使用下三角矩阵（`torch.tril`）将未来位置的注意力权重设为 $-\infty$，确保当前 Token 只能向过去的 Token 汇聚信息。

3. **从单头到多头（Multi-Head Attention）**
   * 单头自注意力就像是只关注一个特定维度的信息（如“寻找前面的动词”）。
   * 多头注意力则并行运行多个自注意力头（运行在各自不同的特征子空间），最后将各头输出拼接并通过一个线性投影层进行融合，极大增强了模型的表达能力。

4. **前馈神经网络（MLP / Feed-Forward Network）**
   * 在注意力机制汇聚所有历史 Token 的特征后，每个 Token 会独立通过一个双层全连接网络（带 ReLU/GELU 激活函数），进行特征的非线性变换与“思考”。

5. **深层网络的优化保障**
   * **残差连接（Skip Connections / Residual Connections）**：通过“捷径（Shortcuts）”使梯度能够无阻碍地反向传播，解决了深层网络梯度消失的问题。
   * **层归一化（Layer Normalization）**：在批次维度之外对特征进行归一化，稳定了深层网络训练的动态范围。视频中强调现代 Transformer 普遍采用 Pre-LN 结构（即在 Self-Attention 和 MLP 之前应用 LayerNorm）。

---

### 💡 实操建议与落地启示
* **掩码（Mask）的高效实现**：在 PyTorch 中，使用 `masked_fill(mask == 0, float('-inf'))` 来阻断注意力流向，这是构建生成式 Decoder 模型的核心标准写法。
* **位置编码（Positional Encoding）的不可或缺**：自注意力机制本身是时序无关的（即打乱输入顺序，结果不变），因此必须加入可学习的位置向量（`nn.Embedding(block_size, n_embd)`）为模型引入位置与顺序的概念。
* **残差连接中的缩放初始化**：在设计具有残差连接的深层网络时，投影层（Projection layers）常进行特殊的标准差初始化（如 $1/\sqrt{2 \times N_{\text{layers}}}$），以控制深度增加时的方差增长。

---

### ⚠️ 局限性与注意事项
* **计算复杂度问题**：自注意力的计算复杂度为 $O(T^2)$，其中 $T$ 是上下文窗口长度（Sequence Length）。这限制了模型在处理极长文本时的计算效率。
* **字符级模型的局限**：本教程为了代码简化使用了字符级（Character-level）的 Tokenizer（词表大小仅 65）。在工业界生产级模型中，必须使用子词（Sub-word）Tokenizer（如 BPE），否则单个词会被切分得过碎，大幅增加了需要处理的上下文长度。