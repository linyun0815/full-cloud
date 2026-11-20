package cn.full.cloud.module.crm.framework.rpc.config;

import cn.full.cloud.module.bpm.api.task.BpmProcessInstanceApi;
import cn.full.cloud.module.system.api.dept.DeptApi;
import cn.full.cloud.module.system.api.dept.PostApi;
import cn.full.cloud.module.system.api.logger.OperateLogApi;
import cn.full.cloud.module.system.api.user.AdminUserApi;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "crmRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = {AdminUserApi.class, DeptApi.class, PostApi.class,
        OperateLogApi.class,
        BpmProcessInstanceApi.class})
public class RpcConfiguration {
}
