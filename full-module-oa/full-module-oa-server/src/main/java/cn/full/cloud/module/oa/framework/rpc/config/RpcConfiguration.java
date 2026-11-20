package cn.full.cloud.module.oa.framework.rpc.config;

import cn.full.cloud.module.bpm.api.task.BpmProcessInstanceApi;
import cn.full.cloud.module.infra.api.file.FileApi;
import cn.full.cloud.module.system.api.dept.DeptApi;
import cn.full.cloud.module.system.api.dict.DictDataApi;
import cn.full.cloud.module.system.api.notify.NotifyMessageSendApi;
import cn.full.cloud.module.system.api.permission.PermissionApi;
import cn.full.cloud.module.system.api.user.AdminUserApi;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "oaRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = {BpmProcessInstanceApi.class, FileApi.class, DeptApi.class, DictDataApi.class,
        NotifyMessageSendApi.class, PermissionApi.class, AdminUserApi.class})
public class RpcConfiguration {
}
