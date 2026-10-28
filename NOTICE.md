# Attribution

Contribution Compass includes or adapts portions and implementation patterns from
[agents-radar](https://github.com/duanyytop/agents-radar), originally copyright
Dylan and licensed under the MIT License.

Adapted areas include bounded GitHub pagination, GitHub Actions workflow patterns, and the idea of
a lightweight static report browser with feeds. Contribution Compass's Python architecture,
configuration model, normalized evidence, event trail, contribution classification, MCP adapter,
and multi-page publication are independent implementations.

The upstream license notice is reproduced below:

> MIT License
>
> Copyright (c) 2026 Dylan
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

## Topic vocabulary

`vocabulary.json` holds data derived from two GitHub-maintained sources, and published
recommendations print the github/explore credit line.

- Topic names, aliases and related topics come from
  [github/explore](https://github.com/github/explore), licensed under
  [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). Contribution Compass keeps
  only the `topic`, `aliases` and `related` fields of each topic page.
- Language names and aliases come from
  [GitHub Linguist](https://github.com/github-linguist/linguist) `languages.yml`,
  Copyright (c) 2017 GitHub, Inc., licensed under the MIT License whose text is reproduced
  above.
- Tag clusters in `clusters.json` are computed with
  [minishlab/potion-base-8M](https://huggingface.co/minishlab/potion-base-8M), licensed
  under the MIT License, through [model2vec](https://github.com/MinishLab/model2vec),
  licensed under the MIT License. The model is downloaded at build time and is not
  redistributed.
