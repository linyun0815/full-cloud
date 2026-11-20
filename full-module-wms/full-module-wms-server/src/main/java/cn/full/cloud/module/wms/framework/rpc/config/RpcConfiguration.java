package cn.full.cloud.module.wms.framework.rpc.config;

import cn.full.cloud.module.system.api.user.AdminUserApi;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "wmsRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = AdminUserApi.class)
public class RpcConfiguration {
}
