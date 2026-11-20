package cn.full.cloud.module.pay.convert.wallet;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.module.pay.controller.admin.wallet.vo.transaction.PayWalletTransactionRespVO;
import cn.full.cloud.module.pay.controller.app.wallet.vo.transaction.AppPayWalletTransactionRespVO;
import cn.full.cloud.module.pay.dal.dataobject.wallet.PayWalletTransactionDO;
import cn.full.cloud.module.pay.service.wallet.bo.WalletTransactionCreateReqBO;
import org.mapstruct.Mapper;
import org.mapstruct.factory.Mappers;

@Mapper
public interface PayWalletTransactionConvert {

    PayWalletTransactionConvert INSTANCE = Mappers.getMapper(PayWalletTransactionConvert.class);

    PageResult<PayWalletTransactionRespVO> convertPage2(PageResult<PayWalletTransactionDO> page);

    PayWalletTransactionDO convert(WalletTransactionCreateReqBO bean);

}
