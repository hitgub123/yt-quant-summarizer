# 🎬 Building makemore Part 5: Building a WaveNet

- **创作者**：`Andrej Karpathy` | **发布日期**：`2026-08-30` | **原视频链接**：[YouTube 视频](https://www.youtube.com/watch?v=t3YJ5hKiMQ0)

---

### 📌 一句话核心主旨 (TL;DR)
本视频通过将之前的多层感知机（MLP）字符预测模型重构为类 WaveNet 的层次树状结构，向观众展示了如何更优雅、更高效地处理和扩展神经网络的上下文窗口（Context Length），从而突破传统平铺连接（Flattening）带来的参数与计算瓶颈。

### 🔍 核心要点精炼拆解 (Key Takeaways)

1. **传统 MLP 架构的上下文瓶颈**
   * 在之前的 MLP 架构中（如 Bengio 等人 2003 年的模型），输入的 $N$ 个字符对应的嵌入向量被直接拉平（Flatten）并拼接成一个超长向量，然后一次性送入隐藏层。
   * **弊端**：这种“一步到位”的平铺导致输入层参数量暴增，无法有效扩展上下文长度，且模型很难在网络深层精细融合不同距离的语义特征。

2. **WaveNet 树状分层融合设计（Hierarchical Fusion）**
   * 采用类似于 WaveNet（扩张因果卷积，Dilated Causal Convolutions）的思想。
   * **机制**：输入不进行整体平铺，而是每 2 个相邻的字符特征先进行融合；在下一层，再将相邻的 2 个双字符融合特征（共 4 个字符的信息）进行二次融合，以此类推。信息在树状网络中逐步逐级汇聚，接收野（Receptive Field）呈指数级扩大。

3. **PyTorch 自定义模块的面向对象重构**
   * 为了支持这种分层组合结构，视频中仿照 PyTorch 官方 API，从零手写重构了几个关键的容器与网络层：
     * `Sequential`：用于链式串联多层结构。
     * `Linear`：全连接层。
     * `BatchNorm1d`：一维批归一化。
     * `Embedding`：词嵌入查找表。
     * `FlattenConsecutive`：**最核心的重构层**。不同于一次性拍平所有维度的 `Flatten`，它只在时序维度（Temporal Dimension）上将相邻的 $2$ 个通道合并，保留其空间/时序步长，为后续的分层线性操作做好形状对齐（Shape Alignment）。

4. **深入理解 Batch Normalization 的张量行为**
   * 视频深入探讨了 `BatchNorm1d` 在输入张量形状为 3D `(B, T, C)` 时的行为。
   * PyTorch 的 `BatchNorm1d` 内部其实在 `dim=0`（Batch 维度）和 `dim=1`（Sequence/Time 维度）上进行了共同均值与方差计算，即它对所有空间位置上的每一个特征通道做归一化，理解这一行为对排查 3D 张量的 Shape 错误至关重要。

---

### 💡 实操建议与落地启示
* **形状诊断习惯**：在重构复杂的深度学习网络层时，务必在正向传播（`forward`）中插入打印张量形状（`shape`）的代码。明确数据在 `(Batch, Time, Channels)` 或 `(N, C, L)` 之间的转换轨迹。
* **分步聚合替代一刀切**：处理时序或高维序列输入时，如果 Transformer 算力受限，可以借鉴 WaveNet 的分组降维思路（使用 Dilated Convolutions 或分组全连接），以 $O(\log N)$ 的层级深度高效提取长程依赖。

---

### ⚠️ 局限性与注意事项
* **时效性与主流架构演进**：WaveNet 模型（卷积/树状 MLP 架构）在音频合成和部分时序任务中表现优异，但在目前的大语言模型（LLM）主流技术栈中，已基本被自注意力机制（Self-Attention）完全取代。
* **调试复杂度增加**：随着网络转为多维时序处理，`BatchNorm` 和 `Linear` 层的输入通道数变化变得极其敏感，若通道数没有成倍对齐（例如 grouping-by-2 时，Context Length 必须为 2 的幂次方），会导致编译或运行期维度不匹配报错。