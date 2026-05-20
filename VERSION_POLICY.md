# Version Policy

webitgpt 在 v1 重寫評比期間只能使用 `1.X.X.X` 版號。

- 不使用 `2.0`、`2.X` 或其他主版號。
- 每次部署修補都必須更新 `VERSION`、`PATCH_ID`、`RELEASE_NOTE`、`BUILD_TIME`。
- `PATCH_ID` 用短英文描述修補目的，方便查 `/health`、頁首、頁尾與 `data/version.json`。
- `CHANGELOG.md` 必須新增對應版本紀錄。

目前主線：`1.0.0.x`
