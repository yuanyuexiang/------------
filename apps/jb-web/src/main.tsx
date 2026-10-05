import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{
      token: { colorPrimary: '#2165e8', colorText: '#1b2c46', colorTextSecondary: '#78879b',
        colorBgLayout: '#f3f6fb', colorBorder: '#e0e6ef', colorBorderSecondary: '#e9edf4',
        borderRadius: 9, fontSize: 14, controlHeight: 36 },
      components: {
        Card: { headerFontSizeSM: 15, headerHeightSM: 52, paddingSM: 20 },
        Table: { headerBg: '#f6f8fc', headerColor: '#63748d', cellPaddingBlockSM: 12, cellPaddingInlineSM: 14 },
        Menu: { darkItemBg: 'transparent', darkSubMenuItemBg: 'transparent',
          darkItemSelectedBg: '#ffffff16', darkItemSelectedColor: '#f5d497', darkItemColor: '#becfea',
          darkItemHoverBg: '#ffffff0c', itemBorderRadius: 9, itemHeight: 44 },
        Tabs: { titleFontSize: 14, horizontalItemGutter: 28 },
      },
    }}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter><App /></BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  </React.StrictMode>,
)
