package cn.full.cloud.module.member.framework.rpc.config;

import cn.full.cloud.module.system.api.logger.LoginLogApi;
import cn.full.cloud.module.system.api.sms.SmsCodeApi;
import cn.full.cloud.module.system.api.social.SocialClientApi;
import cn.full.cloud.module.system.api.social.SocialUserApi;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "memberRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = {SmsCodeApi.class, LoginLogApi.class, SocialUserApi.class, SocialClientApi.class})
public class RpcConfiguration {
}
