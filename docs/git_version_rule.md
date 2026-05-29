# Git Version Rule

每次修改版本號、建立 patch、更新 release note 或完成一個可部署版本，都必須提交到 git。

提交前要先完成可用驗證，至少包含與本次變更相關的 pytest、功能驗證、HTTP read-only check 或手動檢查紀錄。若無法驗證，必須在提交說明、PR 描述或交付摘要中明確寫出原因與替代檢查。

commit message 應包含版本號或 patch id，讓部署版本可以追溯到對應的程式碼、文件與驗證紀錄。
