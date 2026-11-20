package cn.full.cloud.module.pms.framework.rpc.config;

import cn.full.cloud.module.infra.api.file.FileApi;
import cn.full.cloud.module.system.api.dept.DeptApi;
import cn.full.cloud.module.system.api.notify.NotifyMessageSendApi;
import cn.full.cloud.module.system.api.permission.PermissionApi;
import cn.full.cloud.module.system.api.user.AdminUserApi;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "pmsRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = {AdminUserApi.class, DeptApi.class, PermissionApi.class,
        NotifyMessageSendApi.class, FileApi.class})
public class RpcConfiguration {
}
