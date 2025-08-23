/**
 * HTTP请求封装 - AI听世界
 * 基于axios的统一请求处理
 */

class Http {
  constructor() {
    // 创建axios实例
    this.instance = axios.create({
      baseURL: '',  // 移除 /api 前缀，由各页面自己指定完整路径
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    });

    // 请求拦截器
    this.instance.interceptors.request.use(
      config => {
        // 显示加载状态
        this.showLoading();
        
        // 添加时间戳防止缓存
        if (config.method === 'get') {
          config.params = config.params || {};
          config.params._t = Date.now();
        }
        
        return config;
      },
      error => {
        this.hideLoading();
        return Promise.reject(error);
      }
    );

    // 响应拦截器
    this.instance.interceptors.response.use(
      response => {
        this.hideLoading();
        
        // 统一处理响应数据
        if (response.data && response.data.success !== undefined) {
          if (response.data.success) {
            return response.data.data || response.data;
          } else {
            throw new Error(response.data.message || '请求失败');
          }
        }
        
        return response.data;
      },
      error => {
        this.hideLoading();
        
        // 统一错误处理
        let message = '网络请求失败';
        
        if (error.response) {
          // 服务器响应错误
          const { status, data } = error.response;
          
          switch (status) {
            case 400:
              message = data.message || '请求参数错误';
              break;
            case 401:
              message = '未授权访问';
              break;
            case 403:
              message = '禁止访问';
              break;
            case 404:
              message = '请求的资源不存在';
              break;
            case 500:
              message = '服务器内部错误';
              break;
            default:
              message = data.message || `请求失败 (${status})`;
          }
        } else if (error.request) {
          // 网络连接错误
          message = '网络连接失败，请检查网络设置';
        } else {
          // 其他错误
          message = error.message || '未知错误';
        }
        
        this.showError(message);
        return Promise.reject(new Error(message));
      }
    );

    // 加载状态管理
    this.loadingCount = 0;
  }

  /**
   * 显示加载状态
   */
  showLoading() {
    this.loadingCount++;
    
    if (this.loadingCount === 1) {
      // 显示全局loading
      const loading = document.getElementById('global-loading');
      if (loading) {
        loading.style.display = 'flex';
      }
    }
  }

  /**
   * 隐藏加载状态
   */
  hideLoading() {
    this.loadingCount = Math.max(0, this.loadingCount - 1);
    
    if (this.loadingCount === 0) {
      // 隐藏全局loading
      const loading = document.getElementById('global-loading');
      if (loading) {
        loading.style.display = 'none';
      }
    }
  }

  /**
   * 显示错误消息
   */
  showError(message) {
    // 创建临时错误提示
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-toast';
    errorDiv.innerHTML = `
      <div class="error-toast-content">
        <svg class="icon icon-md icon-error" viewBox="0 0 24 24">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
        </svg>
        <span>${message}</span>
      </div>
    `;
    
    // 添加样式
    errorDiv.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: var(--error-color);
      color: white;
      padding: 12px 16px;
      border-radius: var(--radius-medium);
      box-shadow: var(--shadow-medium);
      z-index: 10000;
      animation: slideInRight 0.3s ease-out;
    `;
    
    document.body.appendChild(errorDiv);
    
    // 3秒后自动移除
    setTimeout(() => {
      if (errorDiv.parentNode) {
        errorDiv.remove();
      }
    }, 3000);
  }

  /**
   * GET 请求
   */
  async get(url, params = {}) {
    try {
      const response = await this.instance.get(url, { params });
      return response;
    } catch (error) {
      throw error;
    }
  }

  /**
   * POST 请求
   */
  async post(url, data = {}) {
    try {
      const response = await this.instance.post(url, data);
      return response;
    } catch (error) {
      throw error;
    }
  }

  /**
   * PUT 请求
   */
  async put(url, data = {}) {
    try {
      const response = await this.instance.put(url, data);
      return response;
    } catch (error) {
      throw error;
    }
  }

  /**
   * DELETE 请求
   */
  async delete(url, params = {}) {
    try {
      const response = await this.instance.delete(url, { params });
      return response;
    } catch (error) {
      throw error;
    }
  }

  /**
   * 文件上传
   */
  async upload(url, file, options = {}) {
    const formData = new FormData();
    formData.append('file', file);
    
    // 添加额外参数
    if (options.data) {
      Object.keys(options.data).forEach(key => {
        formData.append(key, options.data[key]);
      });
    }

    try {
      const response = await this.instance.post(url, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        onUploadProgress: options.onProgress || null
      });
      return response;
    } catch (error) {
      throw error;
    }
  }

  /**
   * 下载文件
   */
  async download(url, filename, params = {}) {
    try {
      const response = await this.instance.get(url, {
        params,
        responseType: 'blob'
      });
      
      // 创建下载链接
      const blob = new Blob([response]);
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
      
      return true;
    } catch (error) {
      throw error;
    }
  }

  /**
   * SSE (Server-Sent Events) 连接
   */
  createSSE(url, callbacks = {}) {
    const eventSource = new EventSource(url);
    
    eventSource.onopen = () => {
      console.log('SSE连接已建立');
      if (callbacks.onOpen) callbacks.onOpen();
    };
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (callbacks.onMessage) callbacks.onMessage(data);
      } catch (error) {
        console.error('SSE消息解析失败:', error);
      }
    };
    
    eventSource.onerror = (error) => {
      console.error('SSE连接错误:', error);
      if (callbacks.onError) callbacks.onError(error);
    };
    
    return eventSource;
  }
}

// 创建全局HTTP实例
const http = new Http();

// 导出为全局对象
window.http = http;

// 添加错误提示样式
const style = document.createElement('style');
style.textContent = `
  .error-toast-content {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  @keyframes slideInRight {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
`;
document.head.appendChild(style);
